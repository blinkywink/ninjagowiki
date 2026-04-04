#!/usr/bin/env python3
"""
Update only the hero infobox <aside class="..."> on each character page to match Fandom today.

Uses one API parse per character (overview HTML only). Does not re-import the full article.
Faster than import_all when you only need fresh pi-theme-* / layout classes.

  python3 scripts/sync_character_infobox_theme_classes.py --dry-run
  python3 scripts/sync_character_infobox_theme_classes.py
  python3 scripts/sync_character_infobox_theme_classes.py --limit 5
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DATA_PATH = ROOT / "assets" / "data" / "characters.json"

sys.path.insert(0, str(SCRIPT_DIR))
from import_wiki_character import (  # noqa: E402
    api_parse,
    slug_to_wiki_display,
    split_portable_infobox,
    strip_outer_parser_div,
    wiki_title_from_wiki_url,
)

HERO_BLOCK_RE = re.compile(
    r'(<div\s+class="wiki-char-hero-card wiki-import"[^>]*>\s*)'
    r'(<aside\s+role="region"\s+class=")([^"]*)(")',
    re.IGNORECASE | re.DOTALL,
)


def remote_infobox_class(wiki_page_title: str) -> str | None:
    raw = api_parse(wiki_page_title)
    inner = strip_outer_parser_div(raw)
    aside_html, _ = split_portable_infobox(inner)
    if not aside_html:
        return None
    m = re.search(r"<aside\b[^>]*\bclass=\"([^\"]*)\"", aside_html, re.IGNORECASE)
    return m.group(1).strip() if m else None


def main() -> None:
    ap = argparse.ArgumentParser(description="Sync hero infobox class list from live Fandom.")
    ap.add_argument("--dry-run", action="store_true", help="Print changes only; do not write files.")
    ap.add_argument("--limit", type=int, default=0, help="Process at most N characters (0 = all).")
    ap.add_argument("--delay", type=float, default=0.15, help="Seconds between API calls (default 0.15).")
    args = ap.parse_args()

    with open(DATA_PATH, encoding="utf-8") as f:
        data = json.load(f)
    chars: list[dict] = data["characters"]
    if args.limit and args.limit > 0:
        chars = chars[: args.limit]

    updated = skipped = failed = unchanged = 0

    for i, c in enumerate(chars, start=1):
        slug = (c.get("slug") or "").strip()
        if not slug:
            failed += 1
            continue
        path = ROOT / "characters" / slug / "index.html"
        if not path.is_file():
            skipped += 1
            continue

        wiki_title = wiki_title_from_wiki_url(c.get("wikiUrl") or "") or slug_to_wiki_display(slug)
        print(f"[{i}/{len(chars)}] {slug} ← {wiki_title!r}", file=sys.stderr)

        try:
            new_cls = remote_infobox_class(wiki_title)
        except Exception as e:
            print(f"  ERROR api: {e}", file=sys.stderr)
            failed += 1
            if args.delay > 0:
                time.sleep(args.delay)
            continue

        if not new_cls:
            print("  skip: no infobox on wiki", file=sys.stderr)
            skipped += 1
            if args.delay > 0:
                time.sleep(args.delay)
            continue

        html = path.read_text(encoding="utf-8")
        m = HERO_BLOCK_RE.search(html)
        if not m:
            print("  skip: no hero infobox block in HTML", file=sys.stderr)
            skipped += 1
            if args.delay > 0:
                time.sleep(args.delay)
            continue

        old_cls = m.group(3)
        if old_cls == new_cls:
            unchanged += 1
            if args.delay > 0:
                time.sleep(args.delay)
            continue

        print(f"  class change:\n    was: {old_cls[:120]}{'…' if len(old_cls) > 120 else ''}\n    now: {new_cls[:120]}{'…' if len(new_cls) > 120 else ''}", file=sys.stderr)

        def repl_hero(m: re.Match[str]) -> str:
            return m.group(1) + m.group(2) + new_cls + m.group(4)

        new_html = HERO_BLOCK_RE.sub(repl_hero, html, count=1)
        if not args.dry_run:
            path.write_text(new_html, encoding="utf-8")
        updated += 1

        if args.delay > 0:
            time.sleep(args.delay)

    print(
        f"Done. updated={updated} unchanged={unchanged} skipped={skipped} failed={failed} dry_run={args.dry_run}",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
