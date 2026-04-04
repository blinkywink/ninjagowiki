#!/usr/bin/env python3
"""
Bulk-import Fandom wiki articles into pages/<category-tree>/<slug>/ (from Content tree) and maintain assets/data/wiki_pages.json.

Skips titles that already exist as character articles (characters.json + /characters/<slug>/).

Sources:
  --from-uncovered   assets/data/uncovered_fandom_links.json (sorted by link frequency)
  --from-tree        unique directPages titles from fandom_content_category_tree.json

  python3 scripts/import_wiki_pages_bulk.py --from-uncovered --limit 50 --delay 0.15
  python3 scripts/import_wiki_pages_bulk.py --from-tree --limit 200 --delay 0.12
  python3 scripts/import_wiki_pages_bulk.py --from-uncovered --limit 0   # unlimited (long!)

After a batch:
  python3 scripts/build_site_routes.py
  python3 scripts/rewrite_fandom_character_links.py --apply
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path
from urllib.parse import unquote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WIKI_PAGES_JSON = ROOT / "assets" / "data" / "wiki_pages.json"
UNCOVERED_JSON = ROOT / "assets" / "data" / "uncovered_fandom_links.json"
TREE_JSON = ROOT / "assets" / "data" / "fandom_content_category_tree.json"

sys.path.insert(0, str(SCRIPT_DIR))
from import_wiki_page import import_wiki_page, slugify_page_title, wiki_article_url  # noqa: E402
from wiki_tree_category_paths import (  # noqa: E402
    category_path_for_title,
    load_title_to_category_path,
    pages_article_dir,
)
from rewrite_fandom_character_links import (  # noqa: E402
    build_wiki_path_to_local,
    load_characters,
    wiki_path_from_url,
)


def load_manifest(path: Path) -> dict:
    if not path.is_file():
        return {"v": 1, "pages": []}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def save_manifest(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def title_paths_for_lookup(title: str) -> list[str]:
    """Lowercase /wiki/... path variants for dict lookup."""
    base = ("/wiki/" + title.strip().replace(" ", "_")).lower()
    out = [base]
    if "_" in base:
        out.append(base.replace("_", " "))
    if " " in base:
        out.append(base.replace(" ", "_"))
    return out


def title_is_character(title: str, char_wiki_map: dict[str, str]) -> bool:
    return any(p in char_wiki_map for p in title_paths_for_lookup(title))


def character_slugs(root: Path) -> set[str]:
    slugs: set[str] = set()
    for c in load_characters(root):
        s = (c.get("slug") or "").strip().lower()
        if s:
            slugs.add(s)
    return slugs


def manifest_wiki_path_keys(pages: list[dict]) -> set[str]:
    keys: set[str] = set()
    for p in pages:
        wu = (p.get("wikiUrl") or "").strip()
        path = wiki_path_from_url(wu)
        if not path:
            continue
        pl = path.lower()
        keys.add(pl)
        if "_" in pl:
            keys.add(pl.replace("_", " "))
        if " " in pl:
            keys.add(pl.replace(" ", "_"))
    return keys


def normalized_wiki_path_key(wiki_path: str) -> str:
    """Stable lowercase /wiki/... key for deduping uncovered rows vs manifest."""
    pl = wiki_path.strip().rstrip("/").lower()
    if not pl.startswith("/wiki/"):
        return ""
    return pl


def title_from_sample_href(href: str) -> str:
    """Use sample Fandom URL so API title keeps correct capitalization (wikiPath in JSON is often lowercased)."""
    u = (href or "").strip()
    if not u:
        return ""
    try:
        p = urlparse(u)
    except ValueError:
        return ""
    path = unquote(p.path).rstrip("/")
    if not path.lower().startswith("/wiki/"):
        return ""
    tail = path[6:]
    return tail.replace("_", " ").strip()


def wiki_path_to_title(path: str) -> str:
    pl = path.strip().rstrip("/")
    if not pl.lower().startswith("/wiki/"):
        return ""
    tail = pl[6:]
    return unquote(tail).replace("_", " ").strip()


def iter_uncovered_jobs() -> list[tuple[str, str]]:
    """(normalized_path_key, mediawiki_page_title) in link-frequency order."""
    with open(UNCOVERED_JSON, encoding="utf-8") as f:
        data = json.load(f)
    out: list[tuple[str, str]] = []
    for row in data.get("uncovered") or []:
        wp = row.get("wikiPath") or ""
        pk = normalized_wiki_path_key(wp)
        if not pk:
            continue
        title = title_from_sample_href(row.get("sampleHref") or "") or wiki_path_to_title(wp)
        if title:
            out.append((pk, title))
    return out


def walk_tree_direct_pages(node: dict, into: set[str]) -> None:
    for p in node.get("directPages") or []:
        if isinstance(p, str) and p.strip():
            into.add(p.strip())
    for ch in node.get("children") or []:
        walk_tree_direct_pages(ch, into)


def iter_titles_from_tree() -> list[str]:
    with open(TREE_JSON, encoding="utf-8") as f:
        data = json.load(f)
    seen: set[str] = set()
    walk_tree_direct_pages(data.get("tree") or {}, seen)
    return sorted(seen, key=lambda s: s.lower())


def unique_slug(base: str, used_slugs: set[str]) -> str:
    s = base
    n = 2
    while s in used_slugs:
        s = f"{base}-{n}"
        n += 1
    used_slugs.add(s)
    return s


def main() -> None:
    ap = argparse.ArgumentParser(description="Bulk import wiki articles to /pages/<slug>/.")
    ap.add_argument("--from-uncovered", action="store_true")
    ap.add_argument("--from-tree", action="store_true")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--limit", type=int, default=50, help="Max new imports (0 = no limit).")
    ap.add_argument("--delay", type=float, default=0.15, help="Seconds between API calls.")
    ap.add_argument("--skip-existing", action="store_true", help="Skip if pages/<slug>/index.html exists.")
    args = ap.parse_args()
    root = args.root.resolve()

    if int(args.from_uncovered) + int(args.from_tree) != 1:
        print("Specify exactly one of --from-uncovered or --from-tree", file=sys.stderr)
        sys.exit(2)

    if args.from_uncovered and not UNCOVERED_JSON.is_file():
        print(f"Missing {UNCOVERED_JSON}", file=sys.stderr)
        sys.exit(1)
    if args.from_tree and not TREE_JSON.is_file():
        print(f"Missing {TREE_JSON}", file=sys.stderr)
        sys.exit(1)

    chars = load_characters(root)
    char_wiki_map = build_wiki_path_to_local(root, chars)
    tree_title_to_cat = load_title_to_category_path(root)

    manifest = load_manifest(WIKI_PAGES_JSON)
    pages: list[dict] = list(manifest.get("pages") or [])

    used_slugs: set[str] = {p.get("slug", "").lower() for p in pages if p.get("slug")}
    used_slugs |= character_slugs(root)

    already_paths = manifest_wiki_path_keys(pages)
    uncovered_done: set[str] = set()
    if args.from_uncovered:
        for p in pages:
            wu = (p.get("wikiUrl") or "").strip()
            path = wiki_path_from_url(wu)
            if path:
                uncovered_done.add(path.lower().rstrip("/"))

    def persist_pages() -> None:
        manifest["v"] = 1
        manifest["pages"] = sorted(pages, key=lambda p: (p.get("display") or "").lower())
        save_manifest(WIKI_PAGES_JSON, manifest)

    if args.from_uncovered:
        jobs = iter_uncovered_jobs()
    else:
        jobs = [( "", t) for t in iter_titles_from_tree()]  # path key unused for tree

    imported = 0
    skipped_char = 0
    skipped_manifest = 0
    skipped_exists = 0
    errors = 0

    for item in jobs:
        if args.from_uncovered:
            path_key, title = item
        else:
            path_key, title = item[0], item[1]

        if args.limit and imported >= args.limit:
            break

        if args.from_uncovered and path_key in uncovered_done:
            skipped_manifest += 1
            continue

        if title_is_character(title, char_wiki_map):
            skipped_char += 1
            if args.from_uncovered:
                uncovered_done.add(path_key)
            continue

        if any(p in already_paths for p in title_paths_for_lookup(title)):
            skipped_manifest += 1
            if args.from_uncovered:
                uncovered_done.add(path_key)
            continue

        base_slug = slugify_page_title(title)
        slug = unique_slug(base_slug, used_slugs)

        cat = category_path_for_title(title, tree_title_to_cat)
        out_html = pages_article_dir(root, cat, slug) / "index.html"
        if args.skip_existing and out_html.is_file():
            used_slugs.discard(slug)
            skipped_exists += 1
            if args.from_uncovered:
                uncovered_done.add(path_key)
            continue
        if out_html.is_file():
            used_slugs.discard(slug)
            skipped_exists += 1
            if args.from_uncovered:
                uncovered_done.add(path_key)
            continue

        try:
            _path, slug_used, display, cat_used = import_wiki_page(
                title, slug=slug, category_path=cat, root=root, quiet=True
            )
        except (OSError, RuntimeError, ValueError, FileNotFoundError, KeyError, TypeError) as e:
            print(f"FAIL {title!r}: {e}", file=sys.stderr)
            errors += 1
            used_slugs.discard(slug)
            continue

        wu = wiki_article_url(display)
        href = f"/pages/{cat_used}/{slug_used}"
        kw = display.lower().replace("'", "")
        entry = {
            "slug": slug_used,
            "display": display,
            "wikiTitle": display,
            "wikiUrl": wu,
            "categoryPath": cat_used,
            "href": href,
            "keywords": kw,
            "thumb": "/assets/hero.png",
        }
        pages.append(entry)
        for p in title_paths_for_lookup(display):
            already_paths.add(p)
        if args.from_uncovered:
            uncovered_done.add(path_key)
            ap = wiki_path_from_url(wu)
            if ap:
                uncovered_done.add(ap.lower().rstrip("/"))
        imported += 1
        print(f"[{imported}] {display} → {href}", file=sys.stderr)

        persist_pages()

        if args.delay > 0:
            time.sleep(args.delay)

    persist_pages()

    print(
        f"Done: imported={imported} skipped_char={skipped_char} "
        f"skipped_manifest={skipped_manifest} skipped_existing={skipped_exists} "
        f"errors={errors} total_manifest={len(pages)}",
        file=sys.stderr,
    )
    print("Run: python3 scripts/build_site_routes.py", file=sys.stderr)


if __name__ == "__main__":
    main()
