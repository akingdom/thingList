#!/usr/bin/env python3
# src/build_lists.py

import os, re, json, argparse
from pathlib import Path
from slugify import slugify
import requests_cache, requests
import yaml
import subprocess

GITHUB_API = "https://api.github.com/repos/ai-prompts/prompt-lists/contents/lists/"
BLACKLIST = ['all.yml']

HERE = Path(__file__).resolve().parent
PROJECT_ROOT = HERE.parent
DEFAULT_BUILD = PROJECT_ROOT / "build"
LOCAL_CACHE = PROJECT_ROOT / ".cache" / "prompt-lists"
LISTS_DIR = LOCAL_CACHE / "lists"

def fetch_json(url):
    return requests.get(url).json()

def fetch_text(url):
    return requests.get(url).text

def read_front_matter_file(path):
    text = Path(path).read_text(encoding='utf-8')
    return parse_front_matter_string(text)

def parse_front_matter_string(text):
    if not text.startswith('---'):
        return {}, text
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text
    _, fm_text, body = parts
    meta = yaml.safe_load(fm_text) or {}
    return meta, body

def write_front_matter(path, meta, body):
    front = yaml.safe_dump(meta, sort_keys=False).strip()
    content = "\n".join(['---', front, '---', body.lstrip('\n')])
    Path(path).write_text(content, encoding='utf-8')

def ensure_local_cache():
    if not LOCAL_CACHE.exists():
        print("🔄 Cloning prompt-lists repository into .cache...")
        subprocess.run([
            "git", "clone",
            "https://github.com/ai-prompts/prompt-lists.git",
            str(LOCAL_CACHE)
        ], check=True)
    else:
        print("🗂️ Using local cache from .cache/prompt-lists")

def get_categories(use_local):
    if use_local and LISTS_DIR.exists():
        return [{'type': 'dir', 'name': d.name, 'url': d}
                for d in LISTS_DIR.iterdir() if d.is_dir()]
    else:
        requests_cache.install_cache('.cache', expire_after=3600)
        return fetch_json(GITHUB_API)

def build_data(use_local=True):
    if use_local:
        ensure_local_cache()
    cats = get_categories(use_local)

    cat_dict = {}
    rev_map = {}
    cat_keys = []

    for c in cats:
        if c['type'] != 'dir': continue
        cat = c['name']
        sub_dir = LISTS_DIR / cat if use_local else None
        print(sub_dir)

        if use_local:
            files = [f for f in sub_dir.iterdir() if f.name.endswith('.yml') and f.name not in BLACKLIST]
        else:
            files = fetch_json(c['url'])
            files = [f for f in files if f['name'].endswith('.yml') and f['name'] not in BLACKLIST]

        for f in files:
            name = f.name if use_local else f['name']
            slug = slugify(name[:-4]).lower()
            key = f"{cat}.{slug}"
            raw = Path(f).read_text(encoding='utf-8') if use_local else fetch_text(f['download_url'])
            meta, body = parse_front_matter_string(raw)
            items = [line.strip() for line in body.splitlines() if line.strip()]

            sub = name[:-4]
            cat_dict.setdefault(cat, {})[slug] = {
                'title': meta.get('title', slug),
                'category': cat,
                'list': items
            }

            idx = len(cat_keys)
            cat_keys.append(key)
            for it in items:
                rev_map[it.lower()] = idx

    thingCategories = [
        {'title': cat_dict[cat][sub]['title'], 'category': cat}
        for cat, subs in cat_dict.items() for sub in subs
    ]
    
    if not cat_dict:
        print("⚠️  No categories found—check your local cache path or API response.")


    return cat_dict, thingCategories, rev_map

def write_js(base, cat_dict, thingCategories, rev_map):
    js = Path(base) / "js"
    js.mkdir(parents=True, exist_ok=True)

    with open(js/'categoriesWithThings.js','w', encoding='utf-8') as f:
        f.write("// Auto-generated\n const thingList = ")
        json.dump(cat_dict, f, indent=2, ensure_ascii=False)
        f.write(";\nexport default { thingList };")

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
    p.add_argument("-o", "--output-dir",
                   default=str(DEFAULT_BUILD),
                   help="Directory to write js/ subfolder into")
    p.add_argument("--no-local", action='store_true',
                   help="Force fetching from GitHub API instead of using local cache")
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    cat_dict, thingCategories, rev_map = build_data(use_local=not args.no_local)
    write_js(out_dir, cat_dict, thingCategories, rev_map)
