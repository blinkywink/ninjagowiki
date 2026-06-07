#!/usr/bin/env python3
"""
Build assets/data/site_routes.json for the static site.

Maps Fandom wiki article paths and page titles → local hrefs for pages we actually host
(characters from characters.json; generic articles from pages/<slug>/ via wiki_pages.json).

Used by:
  - all-pages/tree.js (link category “direct pages” to local mirrors when present)
  - Optional future tooling / import pipelines

Also writes assets/data/wiki_search_index.json (v2): mirrored wiki pages + every on-disk character,
with optional searchExcerpt / thumb filled from HTML (default). Use --no-enrich-search for a fast
routes-only pass (subtitles fall back to keywords).

Run after adding characters, wiki page imports, or editing wiki_pages.json.
Also rebuilds browse indexes (episodes, sets, weapons, media) and sitemap.xml.

  python3 scripts/build_site_routes.py
  python3 scripts/build_site_routes.py --no-enrich-search
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
WIKI_SEARCH_INDEX = ROOT / "assets" / "data" / "wiki_search_index.json"

# Reuse the same mapping rules as rewrite_fandom_character_links.py
sys.path.insert(0, str(SCRIPT_DIR))
from rewrite_fandom_character_links import (  # noqa: E402
    build_wiki_path_to_local,
    load_characters,
    local_character_page,
    should_skip_wiki_path,
    wiki_path_from_url,
)


def load_wiki_pages_manifest(root: Path) -> list[dict]:
    p = root / "assets" / "data" / "wiki_pages.json"
    if not p.is_file():
        return []
    with open(p, encoding="utf-8") as f:
        return list(json.load(f).get("pages") or [])


def merge_wiki_pages_into_routes(
    root: Path, wiki_path_to_href: dict[str, str], manifest_rows: list[dict] | None = None
) -> int:
    """Add /pages/... for manifest rows with an on-disk page. Character paths are not overwritten."""
    n = 0
    rows = manifest_rows if manifest_rows is not None else load_wiki_pages_manifest(root)
    for row in rows:
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


def wiki_page_file_for_row(root: Path, row: dict) -> Path | None:
    slug = (row.get("slug") or "").strip()
    if not slug:
        return None
    href_row = (row.get("href") or "").strip()
    if href_row.startswith("/pages/"):
        rel = href_row[len("/pages/") :].strip("/")
        return root.joinpath("pages", *rel.split("/"), "index.html")
    return root / "pages" / slug / "index.html"


def wiki_row_excluded_from_homepage_search(row: dict) -> bool:
    """Skip disambiguation pages and misc / _unsorted bucket from homepage search."""
    href = (row.get("href") or "").strip().lower()
    if "/pages/_unsorted/" in href or href.startswith("/pages/_unsorted/"):
        return True
    cat = (row.get("categoryPath") or "").strip().lower()
    if cat == "_unsorted":
        return True
    title = (row.get("wikiTitle") or row.get("display") or "").lower()
    if "disambiguation" in title:
        return True
    slug = (row.get("slug") or "").lower()
    if "disambiguation" in slug:
        return True
    return False


def build_wiki_search_index_pages(root: Path, manifest_rows: list[dict]) -> list[dict]:
    """Manifest rows that have imported HTML on disk (for homepage search, no 404s)."""
    out: list[dict] = []
    for row in manifest_rows:
        if wiki_row_excluded_from_homepage_search(row):
            continue
        p = wiki_page_file_for_row(root, row)
        if p is None or not p.is_file():
            continue
        out.append(row)
    return out


def enrich_wiki_search_rows(root: Path, rows: list[dict], *, enrich: bool) -> list[dict]:
    """Copy manifest rows; optionally fill searchExcerpt + better thumb from HTML."""
    from search_snippet_extract import (  # noqa: E402
        excerpt_from_mirror_html,
        thumb_from_mirror_html,
    )

    out: list[dict] = []
    for row in rows:
        d = dict(row)
        if _is_generic_search_thumb(d.get("thumb")):
            d.pop("thumb", None)
        if not enrich:
            out.append(d)
            continue
        p = wiki_page_file_for_row(root, d)
        if not p.is_file():
            out.append(d)
            continue
        try:
            ht = p.read_text(encoding="utf-8")
        except OSError:
            ht = ""
        if not ht:
            out.append(d)
            continue
        ex = excerpt_from_mirror_html(ht)
        if ex:
            d["searchExcerpt"] = ex
        th = thumb_from_mirror_html(ht, d.get("thumb"))
        if th and not _is_generic_search_thumb(th):
            d["thumb"] = th
        else:
            d.pop("thumb", None)
        out.append(d)
    return out


def _is_generic_search_thumb(url: str | None) -> bool:
    u = (url or "").strip().lower()
    if u in ("/assets/hero.png", "/assets/hero-mobile.png", ""):
        return True
    if "noimage" in u:
        return True
    return False


def build_character_search_rows(root: Path, characters: list[dict], *, enrich: bool) -> list[dict]:
    """One entry per mirrored character for homepage search (all of characters.json on disk)."""
    from search_snippet_extract import (  # noqa: E402
        excerpt_from_mirror_html,
        thumb_from_mirror_html,
    )

    out: list[dict] = []
    for c in characters:
        slug = (c.get("slug") or "").strip()
        if not slug:
            continue
        if "disambiguation" in slug.lower():
            continue
        ch = local_character_page(root, slug)
        if not ch.is_file():
            continue
        href = (c.get("href") or f"/characters/{slug}").strip().split("?")[0]
        label = (c.get("display") or slug).strip()
        if "disambiguation" in label.lower():
            continue
        filt = (c.get("filter") or label).strip()
        img = (c.get("img") or "").strip()
        row: dict = {
            "kind": "character",
            "href": href,
            "display": label,
            "wikiTitle": label,
            "slug": slug,
            "keywords": filt.lower(),
        }
        if img and not _is_generic_search_thumb(img):
            row["thumb"] = img
        if enrich:
            try:
                ht = ch.read_text(encoding="utf-8")
            except OSError:
                ht = ""
            if ht:
                ex = excerpt_from_mirror_html(ht)
                if ex:
                    row["searchExcerpt"] = ex
                th = thumb_from_mirror_html(ht, row.get("thumb"))
                if th and not _is_generic_search_thumb(th):
                    row["thumb"] = th
                elif not row.get("thumb"):
                    row.pop("thumb", None)
        out.append(row)
    return out


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
    ap.add_argument(
        "--no-enrich-search",
        action="store_true",
        help="Skip scanning HTML for search excerpts/thumbnails (faster; subtitles fall back to keywords).",
    )
    args = ap.parse_args()
    root: Path = args.root.resolve()

    characters = load_characters(root)
    wiki_path_to_href = build_wiki_path_to_local(root, characters)
    manifest_rows = load_wiki_pages_manifest(root)
    wiki_page_routes = merge_wiki_pages_into_routes(root, wiki_path_to_href, manifest_rows)

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

    search_pages = build_wiki_search_index_pages(root, manifest_rows)
    enrich_search = not args.no_enrich_search
    enriched_pages = enrich_wiki_search_rows(root, search_pages, enrich=enrich_search)
    character_search = build_character_search_rows(root, characters, enrich=enrich_search)
    search_payload = {
        "v": 2,
        "generatedAt": payload["generatedAt"],
        "stats": {
            "pagesOnDisk": len(enriched_pages),
            "charactersOnDisk": len(character_search),
            "manifestRows": len(manifest_rows),
            "searchEnrichedFromHtml": enrich_search,
        },
        "pages": enriched_pages,
        "characters": character_search,
    }
    WIKI_SEARCH_INDEX.parent.mkdir(parents=True, exist_ok=True)
    with open(WIKI_SEARCH_INDEX, "w", encoding="utf-8") as f:
        json.dump(search_payload, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(
        f"Wrote {WIKI_SEARCH_INDEX} — {len(enriched_pages)} wiki + {len(character_search)} character entr(y/ies) "
        f"(search enrich={'on' if enrich_search else 'off'}).",
        file=sys.stderr,
    )

    try:
        import build_episodes_index  # noqa: E402

        build_episodes_index.main()
    except Exception as exc:
        print(f"Warning: episodes index not rebuilt ({exc}).", file=sys.stderr)

    try:
        import build_sets_index  # noqa: E402

        build_sets_index.main()
    except Exception as exc:
        print(f"Warning: sets index not rebuilt ({exc}).", file=sys.stderr)

    try:
        import build_weapons_index  # noqa: E402

        build_weapons_index.main()
    except Exception as exc:
        print(f"Warning: weapons index not rebuilt ({exc}).", file=sys.stderr)

    try:
        import build_media_index  # noqa: E402

        build_media_index.main()
    except Exception as exc:
        print(f"Warning: media index not rebuilt ({exc}).", file=sys.stderr)

    try:
        import build_sitemap  # noqa: E402

        build_sitemap.build_sitemap_files(root)
    except Exception as exc:
        print(f"Warning: sitemap not rebuilt ({exc}).", file=sys.stderr)


if __name__ == "__main__":
    main()
