#!/usr/bin/env python3
# src/build_lists.py

import os, re, json
import argparse
from pathlib import Path
from slugify import slugify
import requests_cache, requests
import yaml
from pathlib import Path

GITHUB_API = "https://api.github.com/repos/ai-prompts/prompt-lists/contents/lists/"
BLACKLIST = ['all.yml']

# Compute project root as parent of src/
HERE        = Path(__file__).resolve().parent      # src/
PROJECT_ROOT= HERE.parent                          # project root
DEFAULT_BUILD = PROJECT_ROOT / "build"

def fetch_json(url):
    return requests.get(url).json()

def fetch_text(url):
    return requests.get(url).text

def read_front_matter_file(path):
    """
    Reads a file on disk, returns (meta: dict, body: str).
    """
    text = Path(path).read_text(encoding='utf-8')
    return parse_front_matter_string(text)

def parse_front_matter_string(text):
    """
    Parses text and splits out YAML front matter.

    Returns a tuple: (metadata: dict, body: str).
    If no front matter is present, metadata will be empty.
    """
    # If it doesn’t start with '---', no front matter
    if not text.startswith('---'):
        return {}, text

    # Split into ['', front, body]
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text

    _, fm_text, body = parts
    meta = yaml.safe_load(fm_text) or {}
    return meta, body

def write_front_matter(path, meta, body):
    """
    Serializes metadata as YAML front matter, then writes the file.
    """
    front = yaml.safe_dump(meta, sort_keys=False).strip()
    content = "\n".join([
        '---',
        front,
        '---',
        body.lstrip('\n')  # avoid extra blank line
    ])
    Path(path).write_text(content, encoding='utf-8')

def build_data():
    requests_cache.install_cache('.cache', expire_after=3600)
    cats = fetch_json(GITHUB_API)
    # 1) categoriesWithThings
    cat_dict = {}
    # 2) Collect reverse index entries
    rev_map = {}   # phrase → key
    cat_keys = []  # list of keys in insertion order

    for c in cats:
        if c['type']!='dir': continue
        cat = c['name']
        for f in fetch_json(c['url']):
            name = f['name']
            if any(b in name for b in BLACKLIST): 
                continue
            if not name.endswith('.yml'): 
                continue

            raw_slug = slugify(name[:-4])        # slugify with defaults
            sub_slug = slugify(raw_slug).lower()
            key      = f"{cat}.{sub_slug}"
            raw = fetch_text(f['download_url'])
            meta, body = parse_front_matter_string(raw)
            items = [line.strip() for line in body.splitlines() if line.strip()]

            # populate categoriesWithThings
            sub = name[:-4]
            cat_dict.setdefault(cat, {})[slugify(sub, lowercase=True)] = {
                'title': meta.get('title', sub_slug),
                'category': cat,
                'list': items
            }

            # reverse index
            idx = len(cat_keys)
            cat_keys.append(key)
            for it in items:
                rev_map[it.lower()] = idx

    # build thingCategories array
    thingCategories = [
        {
            'title': cat_dict[cat][sub]['title'],
            'category': cat
        }
        for cat, subs in cat_dict.items()
        for sub in subs
    ]

    return cat_dict, thingCategories, rev_map

def write_js(base, cat_dict, thingCategories, rev_map):
    js_dir = Path(base) / "js"
    js_dir.mkdir(parents=True, exist_ok=True)

    # 1) categoriesWithThings.js
    with open(js/'categoriesWithThings.js','w', encoding='utf-8') as f:
        f.write("// Auto-generated\nexport default ")
        json.dump(cat_dict, f, indent=2, ensure_ascii=False)
        f.write(";\n")

    # 2) thingIndex.js
    with open(js/'thingIndex.js','w', encoding='utf-8') as f:
        f.write("// Auto-generated\n")
        f.write("export const thingCategories = ")
        json.dump(thingCategories, f, indent=2, ensure_ascii=False)
        f.write(";\n\n")

        f.write("export const thingKV = ")
        json.dump(rev_map, f, indent=2, ensure_ascii=False)
        f.write(";\n\n")

        f.write("""export function things(name) {
  const id = thingKV[name.toLowerCase()];
  return id !== undefined ? thingCategories[id] : null;
}

export default { thingCategories, thingKV, things };
""")

def parse_args():
    p = argparse.ArgumentParser(description="Build JS files from prompt lists")
    p.add_argument(
        "-o", "--output-dir",
        default=str(DEFAULT_BUILD),
        help="Directory to write js/ subfolder into, else ../build/ is used"
    )
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    cat_dict, thingCategories, rev_map = build_data()
    write_js(out_dir, cat_dict, thingCategories, rev_map)
