#!/usr/bin/env python3
"""
Append Content category-tree direct page titles that are missing from wiki_pages.json.

Skips titles already covered by characters.json (local /characters/… pages) and
Template:/File:/… style names. After merging, import missing HTML with:

  python3 scripts/refresh_wiki_pages_from_manifest.py --delay 0.12

Then rebuild routes:

  python3 scripts/build_site_routes.py
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from import_wiki_page import slugify_page_title  # noqa: E402
from rewrite_fandom_character_links import load_characters, local_character_page  # noqa: E402
from wiki_tree_category_paths import (  # noqa: E402
    UNSORTED_SEGMENT,
    build_longest_category_path_by_title,
    load_tree,
    norm_wiki_title_key,
)


def norm_title(s: str) -> str:
    return norm_wiki_title_key(s)


def wiki_url_for_title(title: str) -> str:
    path = title.strip().replace(" ", "_")
    q = urllib.parse.quote(path, safe="()'!%")
    return f"https://ninjago.fandom.com/wiki/{q}"


SKIP_TITLE_PREFIXES = (
    "template:",
    "file:",
    "category:",
    "mediawiki:",
    "module:",
    "help:",
)


def should_skip_tree_title(title: str) -> bool:
    t = title.strip()
    if not t:
        return True
    low = t.lower()
    return any(low.startswith(p) for p in SKIP_TITLE_PREFIXES)


def character_title_keys(root: Path) -> set[str]:
    out: set[str] = set()
    for c in load_characters(root):
        slug = (c.get("slug") or "").strip()
        if not slug or not local_character_page(root, slug).is_file():
            continue
        disp = (c.get("display") or "").strip()
        if disp:
            out.add(norm_title(disp))
        wu = (c.get("wikiUrl") or "").strip()
        if "/wiki/" in wu:
            tail = wu.split("/wiki/", 1)[-1].split("?")[0]
            decoded = urllib.parse.unquote(tail).replace("_", " ").strip()
            if decoded:
                out.add(norm_title(decoded))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge missing tree titles into wiki_pages.json")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = args.root.resolve()

    manifest_path = root / "assets" / "data" / "wiki_pages.json"
    with open(manifest_path, encoding="utf-8") as f:
        data = json.load(f)
    pages: list[dict] = list(data.get("pages") or [])

    existing_keys: set[str] = set()
    occupied: set[tuple[str, str]] = set()  # (categoryPath, slug)
    for row in pages:
        t = (row.get("wikiTitle") or row.get("display") or "").strip()
        if t:
            existing_keys.add(norm_title(t))
        cat = (row.get("categoryPath") or "").strip().strip("/")
        slug = (row.get("slug") or "").strip()
        if cat and slug:
            occupied.add((cat, slug))

    tree = load_tree(root)
    title_to_path = build_longest_category_path_by_title(tree)
    char_keys = character_title_keys(root)

    def collect_tree_titles(node: dict, acc: set[str]) -> None:
        for t in node.get("directPages") or []:
            if isinstance(t, str) and t.strip():
                acc.add(t.strip())
        for ch in node.get("children") or []:
            collect_tree_titles(ch, acc)

    tree_titles: set[str] = set()
    collect_tree_titles(tree, tree_titles)

    to_add: list[dict] = []
    for title in sorted(tree_titles, key=lambda s: s.lower()):
        if should_skip_tree_title(title):
            continue
        k = norm_title(title)
        if k in existing_keys or k in char_keys:
            continue
        cat = title_to_path.get(k) or UNSORTED_SEGMENT
        cat = cat.strip().strip("/")
        base_slug = slugify_page_title(title)
        slug = base_slug
        n = 2
        while (cat, slug) in occupied:
            slug = f"{base_slug}-{n}"
            n += 1
        occupied.add((cat, slug))
        existing_keys.add(k)
        href = f"/pages/{cat}/{slug}".replace("//", "/")
        row = {
            "slug": slug,
            "display": title,
            "wikiTitle": title,
            "wikiUrl": wiki_url_for_title(title),
            "categoryPath": cat,
            "href": href,
            "keywords": re.sub(r"\s+", " ", title.lower()),
            "thumb": "/assets/hero.png",
        }
        to_add.append(row)

    print(f"Would append {len(to_add)} manifest rows (tree titles not in wiki_pages / characters).", file=sys.stderr)
    if args.dry_run:
        for r in to_add[:20]:
            print(f"  + {r['wikiTitle']!r} -> {r['href']}", file=sys.stderr)
        if len(to_add) > 20:
            print(f"  … and {len(to_add) - 20} more", file=sys.stderr)
        return

    pages.extend(to_add)
    data["pages"] = pages
    data["v"] = data.get("v") or 1
    with open(manifest_path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    print(f"Wrote {len(pages)} total rows to {manifest_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
