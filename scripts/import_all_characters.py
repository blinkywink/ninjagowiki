#!/usr/bin/env python3
"""Batch-import Fandom character pages into characters/<slug>/index.html and set local hrefs."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
DATA_PATH = ROOT / "assets" / "data" / "characters.json"

sys.path.insert(0, str(SCRIPT_DIR))
from import_wiki_character import (  # noqa: E402
    import_character,
    slug_to_wiki_display,
    wiki_title_from_wiki_url,
)


def load_data() -> dict:
    with open(DATA_PATH, encoding="utf-8") as f:
        return json.load(f)


def save_data(data: dict) -> None:
    tmp = DATA_PATH.with_suffix(".json.tmp")
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, separators=(",", ":"))
        f.write("\n")
    os.replace(tmp, DATA_PATH)


def main() -> None:
    ap = argparse.ArgumentParser(description="Import all characters from characters.json from Fandom.")
    ap.add_argument("--limit", type=int, default=0, help="Import at most N characters (0 = no limit).")
    ap.add_argument(
        "--force",
        action="store_true",
        help="Re-fetch and overwrite existing characters/<slug>/index.html.",
    )
    ap.add_argument(
        "--delay",
        type=float,
        default=0.35,
        help="Seconds to sleep between characters (rate limit; default 0.35).",
    )
    ap.add_argument(
        "--sync-hrefs-from-disk",
        action="store_true",
        help="Set href to /characters/<slug> wherever characters/<slug>/index.html exists; no Fandom fetch.",
    )
    args = ap.parse_args()

    data = load_data()

    if args.sync_hrefs_from_disk:
        updated = 0
        for c in data["characters"]:
            slug = c.get("slug") or ""
            if not slug:
                continue
            out_html = ROOT / "characters" / slug / "index.html"
            if not out_html.is_file():
                continue
            local_href = f"/characters/{slug}"
            if c.get("href") != local_href:
                c["href"] = local_href
                updated += 1
        if updated:
            save_data(data)
        print(
            f"sync-hrefs-from-disk: updated {updated} hrefs (of {len(data['characters'])} rows).",
            file=sys.stderr,
        )
        return

    chars: list[dict] = data["characters"]
    total = len(chars)
    if args.limit and args.limit > 0:
        chars = chars[: args.limit]

    ok = skip = fail = 0

    for i, c in enumerate(chars, start=1):
        slug = c.get("slug") or ""
        if not slug:
            print(f"[{i}/{len(chars)}] skip: missing slug {c!r}", file=sys.stderr)
            fail += 1
            continue
        wiki_url = c.get("wikiUrl") or ""
        wiki_title = wiki_title_from_wiki_url(wiki_url) or slug_to_wiki_display(slug)
        display = (c.get("display") or wiki_title).strip() or wiki_title
        local_href = f"/characters/{slug}"
        out_html = ROOT / "characters" / slug / "index.html"

        if not args.force and out_html.is_file():
            if c.get("href") != local_href:
                c["href"] = local_href
                save_data(data)
            skip += 1
            print(f"[{i}/{len(chars)}] skip existing: {slug}", file=sys.stderr)
            if args.delay > 0 and i < len(chars):
                time.sleep(args.delay)
            continue

        print(f"[{i}/{len(chars)}] import: {slug} ({wiki_title!r})", file=sys.stderr)
        try:
            import_character(slug, display, wiki_title, root=ROOT, quiet=True)
        except Exception as e:
            print(f"  ERROR {slug}: {e}", file=sys.stderr)
            fail += 1
            if args.delay > 0 and i < len(chars):
                time.sleep(args.delay)
            continue

        if c.get("href") != local_href:
            c["href"] = local_href
            save_data(data)
        ok += 1
        if args.delay > 0 and i < len(chars):
            time.sleep(args.delay)

    print(
        f"Done. imported={ok} skipped={skip} failed={fail} (of {len(chars)} processed; "
        f"{total} in file).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
