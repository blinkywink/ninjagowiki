#!/usr/bin/env python3
"""
Lay out mirrored wiki pages under pages/<Content-tree>/<slug>/ to match the category tree.

Reads assets/data/wiki_pages.json and fandom_content_category_tree.json, moves each
pages/<slug>/ folder to pages/<longest-matching-category-path>/<slug>/, and updates
categoryPath + href on every row. Titles with no directPages entry use _unsorted.

Afterward run:
  python3 scripts/build_site_routes.py
  python3 scripts/rewrite_fandom_character_links.py --apply
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WIKI_PAGES_JSON = ROOT / "assets" / "data" / "wiki_pages.json"

sys.path.insert(0, str(SCRIPT_DIR))
from wiki_tree_category_paths import (  # noqa: E402
    category_path_for_title,
    load_title_to_category_path,
    pages_article_dir,
)


def load_manifest(path: Path) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def prune_empty_parents(pages_root: Path, start: Path) -> None:
    cur = start.resolve()
    root = pages_root.resolve()
    while cur != root and cur.is_dir():
        nxt = cur.parent
        try:
            if not any(cur.iterdir()):
                cur.rmdir()
        except OSError:
            break
        cur = nxt


def main() -> None:
    ap = argparse.ArgumentParser(description="Move flat /pages/<slug>/ into tree paths.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Print planned moves only; do not write JSON or move files.",
    )
    args = ap.parse_args()
    root = args.root.resolve()

    if not WIKI_PAGES_JSON.is_file():
        print(f"Missing {WIKI_PAGES_JSON}", file=sys.stderr)
        sys.exit(1)

    title_map = load_title_to_category_path(root)
    data = load_manifest(WIKI_PAGES_JSON)
    pages = list(data.get("pages") or [])

    moved = 0
    cleaned = 0
    missing = 0

    for row in pages:
        slug = (row.get("slug") or "").strip()
        title = (row.get("wikiTitle") or row.get("display") or "").strip()
        if not slug or not title:
            continue

        cat = category_path_for_title(title, title_map)
        new_dir = pages_article_dir(root, cat, slug)
        old_dir = root / "pages" / slug
        new_idx = new_dir / "index.html"
        old_idx = old_dir / "index.html"
        href = f"/pages/{cat}/{slug}"
        row["categoryPath"] = cat
        row["href"] = href

        if new_idx.is_file():
            if old_idx.is_file() and old_dir.resolve() != new_dir.resolve():
                if args.dry_run:
                    print(f"RMDIR duplicate flat {old_dir}", file=sys.stderr)
                else:
                    shutil.rmtree(old_dir, ignore_errors=True)
                    prune_empty_parents(root / "pages", old_dir.parent)
                cleaned += 1
            continue

        if old_idx.is_file():
            if args.dry_run:
                print(f"MOVE {old_dir} -> {new_dir}", file=sys.stderr)
            else:
                new_dir.parent.mkdir(parents=True, exist_ok=True)
                if new_dir.exists():
                    shutil.rmtree(new_dir, ignore_errors=True)
                shutil.move(str(old_dir), str(new_dir))
                prune_empty_parents(root / "pages", old_dir.parent)
            moved += 1
            continue

        missing += 1

    data["v"] = 1
    data["pages"] = sorted(pages, key=lambda p: (p.get("display") or "").lower())

    if not args.dry_run:
        save_manifest(WIKI_PAGES_JSON, data)

    print(
        f"{'DRY-RUN ' if args.dry_run else ''}moved={moved} removed_dup_flat={cleaned} "
        f"missing_on_disk={missing}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
