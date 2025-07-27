#!/usr/bin/env python3
# src/build_lists.py

import argparse
import json
import subprocess
from pathlib import Path

import requests
import requests_cache
import yaml
from slugify import slugify

GITHUB_API    = "https://api.github.com/repos/ai-prompts/prompt-lists/contents/lists/"
BLACKLIST     = ['all.yml']
HERE          = Path(__file__).resolve().parent
PROJECT_ROOT  = HERE.parent
DEFAULT_BUILD = PROJECT_ROOT / "build"
LOCAL_CACHE   = PROJECT_ROOT / ".cache" / "prompt-lists"
LISTS_DIR     = LOCAL_CACHE / "lists"

def fetch_json(url):
    return requests.get(url).json()

def fetch_text(url):
    return requests.get(url).text

def parse_front_matter_string(text):
    if not text.startswith('---'):
        return {}, text
    parts = text.split('---', 2)
    if len(parts) < 3:
        return {}, text
    _, fm, body = parts
    meta = yaml.safe_load(fm) or {}
    return meta, body

def ensure_local_cache():
    if not LOCAL_CACHE.exists():
        print("🔄 Cloning prompt-lists into .cache/prompt-lists…")
        subprocess.run([
            "git", "clone",
            "https://github.com/ai-prompts/prompt-lists.git",
            str(LOCAL_CACHE)
        ], check=True)
    else:
        print("🗂️ Using local cache at .cache/prompt-lists")

def get_categories(use_local):
    if use_local and LISTS_DIR.exists():
        # Only subfolders under lists/ are real categories
        return [
            {'type': 'dir', 'name': d.name}
            for d in LISTS_DIR.iterdir() if d.is_dir()
        ]
    else:
        requests_cache.install_cache('.cache', expire_after=3600)
        return fetch_json(GITHUB_API)

def build_data(use_local=True):
    if use_local:
        ensure_local_cache()

    cats     = get_categories(use_local)
    cat_dict = {}
    rev_map  = {}
    cat_keys = []

    for c in cats:
        if c['type'] != 'dir':
            continue

        cat     = c['name']
        sub_dir = LISTS_DIR / cat if use_local else None

        if use_local:
            files = [
                f for f in sub_dir.iterdir()
                if f.suffix == '.yml' and f.name not in BLACKLIST
            ]
        else:
            api_files = fetch_json(c['url'])
            files = [
                f for f in api_files
                if f['name'].endswith('.yml') and f['name'] not in BLACKLIST
            ]

        for f in files:
            name = f.name if use_local else f['name']
            slug = slugify(name[:-4]).lower()
            key  = f"{cat}.{slug}"

            raw = (Path(f).read_text(encoding='utf-8')
                   if use_local else
                   fetch_text(f['download_url']))

            meta, body = parse_front_matter_string(raw)
            items = [ln.strip() for ln in body.splitlines() if ln.strip()]

            cat_dict.setdefault(cat, {})[slug] = {
                'title':    meta.get('title', slug),
                'category': cat,
                'list':     items
            }

            idx = len(cat_keys)
            cat_keys.append(key)
            for it in items:
                rev_map[it.lower()] = idx

    thing_categories = [
        {'title': cat_dict[c][s]['title'], 'category': c}
        for c, subs in cat_dict.items()
        for s in subs
    ]

    if not cat_dict:
        print("⚠️  No categories found—check your cache or API response.")

    return cat_dict, thing_categories, rev_map

def write_js(base, cat_dict, thing_categories, rev_map):
    js_dir = Path(base) / "js"
    js_dir.mkdir(parents=True, exist_ok=True)

    # Pre-serialize JSON for consistent formatting
    tl_json = json.dumps(cat_dict, ensure_ascii=False, indent=2)
    tc_json = json.dumps(thing_categories, ensure_ascii=False, indent=2)
    kv_json = json.dumps(rev_map, ensure_ascii=False, indent=2)

    # 1) categoriesWithThings.js
    out1 = js_dir / "categoriesWithThings.js"
    with open(out1, "w", encoding="utf-8") as f:
        f.write(
f"""/*!
 * categoriesWithThings.js v1.0.0
 * Auto-generated – do not edit.
 *
 * UMD module exporting `thingList`
 *
 * Exports
 *   • thingList – an object of categories → lists
 *
 * Usage
 *   AMD (RequireJS):
 *     define(['categoriesWithThings'], function(api) {{
 *       console.log(api.thingList);
 *     }});
 *
 *   CommonJS / Node:
 *     const {{ thingList }} = require('categoriesWithThings');
 *     console.log(thingList);
 *
 *   Browser global:
 *     console.log(window.categoriesWithThings.thingList);
 */
(function (root, factory) {{
  if (typeof define === 'function' && define.amd) {{
    define([], factory);
  }} else if (typeof module === 'object' && module.exports) {{
    module.exports = factory();
  }} else {{
    root.categoriesWithThings = factory();
  }}
}}(typeof self !== 'undefined' ? self : this, function () {{
  const thingList = {tl_json};
  return {{ thingList }};
}}));
""")

    # 2) thingIndex.js
    out2 = js_dir / "thingIndex.js"
    with open(out2, "w", encoding="utf-8") as f:
        f.write(
f"""/*!
 * thingList.js v1.0.0
 * Auto-generated – do not edit.
 *
 * UMD module exporting `thingList`
 *
 * Exports
 *   • thingList – object mapping categories to their thing arrays
 *
 * Usage
 *   AMD (RequireJS):
 *     define(['thingList'], function(api) {{
 *       console.log(api.thingList);
 *     }});
 *
 *   CommonJS / Node:
 *     const {{ thingList }} = require('thingList');
 *     console.log(thingList);
 *
 *   Browser global:
 *     console.log(window.thingList);
 */
(function (root, factory) {{
  if (typeof define === 'function' && define.amd) {{
    define([], factory);
  }} else if (typeof module === 'object' && module.exports) {{
    module.exports = factory();
  }} else {{
    root.thingIndex = factory();
  }}
}}(typeof self !== 'undefined' ? self : this, function () {{
  const thingCategories = {tc_json};
  const thingKV         = {kv_json};

  function things(name) {{
    const id = thingKV[name.toLowerCase()];
    return id !== undefined ? thingCategories[id] : null;
  }}

  return {{ thingCategories, thingKV, things }};
}}));
""")

    print(f"✅ Wrote UMD bundles to:\n  • {out1}\n  • {out2}")

def parse_args():
    p = argparse.ArgumentParser(
        description="Build UMD-wrapped JS bundles from prompt lists"
    )
    p.add_argument(
        "-o", "--output-dir",
        default=str(DEFAULT_BUILD),
        help="Directory to write js/ subfolder into"
    )
    p.add_argument(
        "--no-local", action="store_true",
        help="Skip local .cache and always fetch from GitHub API"
    )
    return p.parse_args()

if __name__ == "__main__":
    args = parse_args()
    out_dir = Path(args.output_dir).resolve()
    cat_dict, thing_categories, rev_map = build_data(use_local=not args.no_local)
    write_js(out_dir, cat_dict, thing_categories, rev_map)
