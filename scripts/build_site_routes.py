#!/usr/bin/env python3
"""
Build assets/data/site_routes.json for the static site.

Maps Fandom wiki article paths and page titles → local hrefs for pages we actually host
(characters from characters.json; generic articles from pages/<slug>/ via wiki_pages.json).

Used by:
  - all-pages/tree.js (link category “direct pages” to local mirrors when present)
  - Optional future tooling / import pipelines

Run after adding characters, wiki page imports, or editing wiki_pages.json:

  python3 scripts/build_site_routes.py
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import unquote

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
OUT = ROOT / "assets" / "data" / "site_routes.json"

# Reuse the same mapping rules as rewrite_fandom_character_links.py
sys.path.insert(0, str(SCRIPT_DIR))
from rewrite_fandom_character_links import (  # noqa: E402
    build_wiki_path_to_local,
    load_characters,
    should_skip_wiki_path,
    wiki_path_from_url,
)


def load_wiki_pages_manifest(root: Path) -> list[dict]:
    p = root / "assets" / "data" / "wiki_pages.json"
    if not p.is_file():
        return []
    with open(p, encoding="utf-8") as f:
        return list(json.load(f).get("pages") or [])


def merge_wiki_pages_into_routes(root: Path, wiki_path_to_href: dict[str, str]) -> int:
    """Add /pages/... for manifest rows with an on-disk page. Character paths are not overwritten."""
    n = 0
    for row in load_wiki_pages_manifest(root):
        slug = (row.get("slug") or "").strip()
        if not slug:
            continue
        href_row = (row.get("href") or "").strip()
        if href_row.startswith("/pages/"):
            rel = href_row[len("/pages/") :].strip("/")
            page_file = root.joinpath("pages", *rel.split("/"), "index.html")
        else:
            page_file = root / "pages" / slug / "index.html"
        if not page_file.is_file():
            continue
        wu = (row.get("wikiUrl") or "").strip()
        path = wiki_path_from_url(wu)
        if not path:
            continue
        pl = path.lower()
        if should_skip_wiki_path(pl):
            continue
        local_href = href_row if href_row.startswith("/pages/") else f"/pages/{slug}"
        if pl not in wiki_path_to_href:
            wiki_path_to_href[pl] = local_href
            n += 1
        pl_us = pl.replace("_", " ") if "_" in pl else None
        if pl_us and pl_us not in wiki_path_to_href:
            wiki_path_to_href[pl_us] = local_href
        pl_un = pl.replace(" ", "_") if " " in pl else None
        if pl_un and pl_un not in wiki_path_to_href:
            wiki_path_to_href[pl_un] = local_href
    return n


def wiki_title_from_path(path: str) -> str:
    """'/wiki/Foo_bar' -> 'Foo bar' (decoded, for API-style titles)."""
    p = path.strip().rstrip("/")
    if not p.lower().startswith("/wiki/"):
        return ""
    tail = p[6:]
    return unquote(tail).replace("_", " ").strip()


def main() -> None:
    ap = argparse.ArgumentParser(description="Write site_routes.json (wiki → local href).")
    ap.add_argument("--root", type=Path, default=ROOT, help="Site root")
    ap.add_argument("-o", "--output", type=Path, default=OUT, help="Output JSON path")
    args = ap.parse_args()
    root: Path = args.root.resolve()

    characters = load_characters(root)
    wiki_path_to_href = build_wiki_path_to_local(root, characters)
    wiki_page_routes = merge_wiki_pages_into_routes(root, wiki_path_to_href)

    wiki_title_key_to_href: dict[str, str] = {}
    for path, href in wiki_path_to_href.items():
        if not path.startswith("/wiki/"):
            continue
        title = wiki_title_from_path(path)
        if not title:
            continue
        key = title.lower()
        if key not in wiki_title_key_to_href:
            wiki_title_key_to_href[key] = href

    payload = {
        "v": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "wikiPathToHref": dict(sorted(wiki_path_to_href.items())),
        "wikiTitleKeyToHref": dict(sorted(wiki_title_key_to_href.items())),
        "stats": {
            "characterManifestRows": len(characters),
            "wikiPageRouteRowsAdded": wiki_page_routes,
            "wikiPathsMapped": len(wiki_path_to_href),
            "wikiTitlesMapped": len(wiki_title_key_to_href),
        },
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    print(
        f"Wrote {args.output} — {payload['stats']['wikiPathsMapped']} paths, "
        f"{payload['stats']['wikiTitlesMapped']} title keys "
        f"({payload['stats']['wikiPageRouteRowsAdded']} from wiki_pages.json).",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()
