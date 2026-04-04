#!/usr/bin/env python3
"""
Re-fetch every entry in assets/data/wiki_pages.json and rewrite pages/<slug>/index.html.

Use after changing import_wiki_page layout (e.g. to match character pages).

  python3 scripts/refresh_wiki_pages_from_manifest.py --delay 0.12
  python3 scripts/refresh_wiki_pages_from_manifest.py --limit 20   # smoke test
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


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-import all wiki_pages.json rows in place.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--delay", type=float, default=0.12)
    ap.add_argument("--limit", type=int, default=0, help="Max pages (0 = all).")
    args = ap.parse_args()
    root = args.root.resolve()

    if not WIKI_PAGES_JSON.is_file():
        print(f"Missing {WIKI_PAGES_JSON}", file=sys.stderr)
        sys.exit(1)

    with open(WIKI_PAGES_JSON, encoding="utf-8") as f:
        data = json.load(f)
    rows = list(data.get("pages") or [])
    if args.limit:
        rows = rows[: args.limit]

    ok = 0
    err = 0
    for i, row in enumerate(rows):
        slug = (row.get("slug") or "").strip()
        title = (row.get("wikiTitle") or row.get("display") or "").strip()
        if not slug or not title:
            print(f"SKIP bad row {i}: {row!r}", file=sys.stderr)
            err += 1
            continue
        try:
            cat = (row.get("categoryPath") or "").strip() or None
            import_wiki_page(title, slug=slug, category_path=cat, root=root, quiet=True)
        except (OSError, RuntimeError, ValueError, FileNotFoundError, KeyError, TypeError) as e:
            print(f"FAIL {slug!r} ({title!r}): {e}", file=sys.stderr)
            err += 1
            continue
        ok += 1
        if ok % 50 == 0:
            print(f"… {ok}/{len(rows)}", file=sys.stderr, flush=True)
        if args.delay > 0:
            time.sleep(args.delay)

    print(f"Done: refreshed={ok} errors={err} total_rows={len(rows)}", file=sys.stderr, flush=True)


if __name__ == "__main__":
    main()
