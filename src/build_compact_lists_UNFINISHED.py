#!/usr/bin/env python3
# src/build_compact_lists.py
import re
import yaml
import argparse
from collections import OrderedDict
from pathlib import Path
from slugify import slugify
import requests_cache, requests

BLACKLIST = ['all.yml']
GITHUB_API = "https://api.github.com/repos/ai-prompts/prompt-lists/contents/lists/"

def fetch_json(url):
    r = requests.get(url); r.raise_for_status(); return r.json()

def fetch_text(url):
    r = requests.get(url); r.raise_for_status(); return r.text

def parse_frontmatter(text):
    if not text.startswith('---'):
        return {}, text
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text
    _, fm, body = parts
    return yaml.safe_load(fm) or {}, body

def extract_markdown_block(js_text):
    """
    Returns (prefix, md_block, suffix) where md_block is the raw lines
    between the backticks of allPromptDataMarkdown.
    """
    pattern = re.compile(
        r"(const\s+allPromptDataMarkdown\s*=\s*`)([\s\S]*?)(`;)",
        re.MULTILINE
    )
    m = pattern.search(js_text)
    if not m:
        raise RuntimeError("Couldn't find allPromptDataMarkdown block")
    return m.group(1), m.group(2).strip(), m.group(3)

def parse_clusters_md(md_block):
    """
    Parse lines like:
      ### key
      - terms: a, b, c
      - associates: x, y
    into an OrderedDict(key -> {'terms':[], 'associates':[]})
    """
    clusters = OrderedDict()
    current = None
    for line in md_block.splitlines():
        line = line.strip()
        if line.startswith("### "):
            current = line[4:].strip()
            clusters[current] = {'terms': [], 'associates': []}
        elif current and line.startswith("- terms:"):
            parts = line[len("- terms:"):].strip()
            clusters[current]['terms'] = [t.strip() for t in parts.split(',') if t.strip()]
        elif current and line.startswith("- associates:"):
            parts = line[len("- associates:"):].strip()
            clusters[current]['associates'] = [a.strip() for a in parts.split(',') if a.strip()]
    return clusters

def fetch_yaml_clusters():
    """
    Fetch every <cat>/<file>.yml, parse frontmatter+body,
    return dict(conceptKey -> terms-list).
    """
    requests_cache.install_cache(".cache", expire_after=3600)
    cats = fetch_json(GITHUB_API)
    new_clusters = {}
    for c in cats:
        if c['type'] != 'dir': continue
        for f in fetch_json(c['url']):
            name = f['name']
            if not name.endswith('.yml') or any(b in name for b in BLACKLIST):
                continue
            raw = fetch_text(f['download_url'])
            _, body = parse_frontmatter(raw)
            key = slugify(name[:-4]).lower()
            terms = [l.strip() for l in body.splitlines() if l.strip()]
            new_clusters[key] = terms
    return new_clusters

def merge_clusters(old, new):
    """
    old: OrderedDict of existing clusters with 'terms' + 'associates'
    new: dict(key -> new term list)
    Returns a new OrderedDict in which:
      - for key in new: use new[ key ] as .terms but keep old[ key ].associates
      - for key only in old: keep it unchanged
      - for key only in new: append at end (with empty associates)
    """
    merged = OrderedDict()
    # First, all old keys
    for key, data in old.items():
        terms = new.get(key, data['terms'])
        assoc = data['associates']
        merged[key] = {'terms': terms, 'associates': assoc}
    # Then any brand-new keys
    for key, terms in new.items():
        if key not in merged:
            merged[key] = {'terms': terms, 'associates': []}
    return merged

def build_md_from_clusters(clusters, compact=False):
    sep = "," if compact else ", "
    nl  = ""  if compact else "\n"
    parts = ["# Prompt Clusters Data"]
    for key, data in clusters.items():
        parts.append(f"### {key}")
        parts.append(f"- terms:{sep.join(data['terms'])}")
        parts.append(f"- associates:{sep.join(data['associates'])}")
        if not compact:
            parts.append("")  # blank line
    text = nl.join(parts).strip()
    return text

def replace_block(js_text, prefix, new_md, suffix):
    return prefix + "\n" + new_md + "\n" + suffix.join(js_text.split(prefix,1)[1].split(suffix,1)[1:])

def main():
    p = argparse.ArgumentParser()
    p.add_argument("--input",  required=True, help="Existing promptClusters.js")
    p.add_argument("--output", required=True, help="Where to write merged JS")
    p.add_argument("--compact", action="store_true", help="No spaces/blank lines")
    args = p.parse_args()

    js_text = Path(args.input).read_text(encoding="utf-8")
    prefix, old_md, suffix = extract_markdown_block(js_text)
    old_clusters = parse_clusters_md(old_md)
    new_clusters = fetch_yaml_clusters()
    merged      = merge_clusters(old_clusters, new_clusters)
    merged_md   = build_md_from_clusters(merged, compact=args.compact)

    updated = replace_block(js_text, prefix, merged_md, suffix)
    Path(args.output).parent.mkdir(parents=True, exist_ok=True)
    Path(args.output).write_text(updated, encoding="utf-8")
    print(f"✅ Merged data written to {args.output}")

if __name__ == "__main__":
    main()
