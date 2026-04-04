#!/usr/bin/env python3
"""
Import wiki articles for manifest rows whose index.html does not exist yet.

  python3 scripts/import_missing_wiki_pages_from_manifest.py --delay 0.12
  python3 scripts/import_missing_wiki_pages_from_manifest.py --limit 100
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WIKI_PAGES_JSON = ROOT / "assets" / "data" / "wiki_pages.json"

sys.path.insert(0, str(SCRIPT_DIR))
from import_wiki_page import import_wiki_page  # noqa: E402


def page_path_for_row(root: Path, row: dict) -> Path | None:
    href = (row.get("href") or "").strip()
    if href.startswith("/pages/"):
        rel = href[len("/pages/") :].strip("/")
        return root.joinpath("pages", *rel.split("/"), "index.html")
    slug = (row.get("slug") or "").strip()
    if not slug:
        return None
    return root / "pages" / slug / "index.html"


def main() -> None:
    ap = argparse.ArgumentParser(description="Import manifest rows missing on disk.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--delay", type=float, default=0.12)
    ap.add_argument("--limit", type=int, default=0, help="Max imports (0 = no limit).")
    args = ap.parse_args()
    root = args.root.resolve()

    if not WIKI_PAGES_JSON.is_file():
        print(f"Missing {WIKI_PAGES_JSON}", file=sys.stderr)
        sys.exit(1)

    with open(WIKI_PAGES_JSON, encoding="utf-8") as f:
        rows = list(json.load(f).get("pages") or [])

    missing: list[dict] = []
    for row in rows:
        p = page_path_for_row(root, row)
        if p is None or p.is_file():
            continue
        missing.append(row)

    if args.limit:
        missing = missing[: args.limit]

    print(f"Missing on disk: {len(missing)} row(s) to import.", file=sys.stderr)
    ok = err = 0
    for i, row in enumerate(missing):
        slug = (row.get("slug") or "").strip()
        title = (row.get("wikiTitle") or row.get("display") or "").strip()
        if not slug or not title:
            err += 1
            continue
        try:
            cat = (row.get("categoryPath") or "").strip() or None
            import_wiki_page(title, slug=slug, category_path=cat, root=root, quiet=True)
            ok += 1
        except (OSError, RuntimeError, ValueError, FileNotFoundError, KeyError, TypeError) as e:
            print(f"FAIL {slug!r} ({title!r}): {e}", file=sys.stderr)
            err += 1
            continue
        if ok % 25 == 0:
            print(f"… {ok} imported", file=sys.stderr, flush=True)
        if args.delay > 0:
            time.sleep(args.delay)

    print(f"Done: imported={ok} errors={err}", file=sys.stderr)


if __name__ == "__main__":
    main()
