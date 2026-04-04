#!/usr/bin/env python3
"""
Import a single main-namespace Fandom wiki article as a static page at pages/<slug>/index.html.

Uses the same HTML shell, TOC rail, infobox rail, overview prose, lightbox, and tab JS as
character imports (import_wiki_character.TEMPLATE).

  python3 scripts/import_wiki_page.py "Season 15: Crystalized"
  python3 scripts/import_wiki_page.py --slug crystalized-season "Season 15: Crystalized"

Does not replace character pages — use import_wiki_character for those.
"""

from __future__ import annotations

import argparse
import html
import re
import sys
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from import_wiki_character import (  # noqa: E402
    TEMPLATE,
    api_parse,
    build_hero_card_html,
    build_overview_panel_html,
    build_toc_sidebar_and_split_class,
    build_wiki_char_panels_html,
    build_wiki_char_tabs_html,
    dedupe_toc_ids_in_full_page,
    extract_first_toc_block,
    rewrite_wiki_html,
    split_portable_infobox,
    strip_outer_parser_div,
    wrap_overview_h2_sections,
)
from wiki_tree_category_paths import (  # noqa: E402
    build_content_mirror_breadcrumb_nav_html,
    category_path_for_title,
    load_title_to_category_path,
    load_tree,
    pages_article_dir,
)

BASE = "https://ninjago.fandom.com"


def slugify_page_title(title: str) -> str:
    t = title.strip().lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"[-\s]+", "-", t).strip("-")
    return t or "page"


def wiki_article_url(title: str) -> str:
    path = title.strip().replace(" ", "_")
    q = urllib.parse.quote(path, safe="()'!%")
    return f"{BASE}/wiki/{q}"


def import_wiki_page(
    wiki_page_title: str,
    *,
    slug: str | None = None,
    category_path: str | None = None,
    root: Path | None = None,
    quiet: bool = False,
) -> tuple[Path, str, str, str]:
    """
    Write pages/<category-path>/<slug>/index.html (mirrors Content tree layout).

    Returns (out_path, slug, display_title, category_path_used).
    If category_path is None, resolves from fandom_content_category_tree.json (else _unsorted).
    """
    root = root or ROOT
    title = wiki_page_title.strip()
    if not title:
        raise ValueError("empty wiki page title")

    if not quiet:
        print(f"Fetching… {title!r}", file=sys.stderr)

    raw = api_parse(title)
    if not raw or not str(raw).strip():
        raise FileNotFoundError(f"No wiki page: {title!r}")

    inner = strip_outer_parser_div(raw)
    body_html = rewrite_wiki_html(inner)
    if not body_html.strip():
        raise ValueError(f"Empty body after rewrite: {title!r}")

    overview_no_toc, toc_overview = extract_first_toc_block(body_html)
    infobox_html, overview_prose = split_portable_infobox(overview_no_toc)
    overview_prose = wrap_overview_h2_sections(overview_prose)
    hero_card = build_hero_card_html(infobox_html)

    parts = {"overview": build_overview_panel_html(overview_prose)}
    visible_tab_keys: tuple[str, ...] = ("overview",)
    toc_map = {"overview": toc_overview}
    toc_sidebar, split_cls = build_toc_sidebar_and_split_class(toc_map, visible_tab_keys)
    wiki_char_tabs = build_wiki_char_tabs_html(visible_tab_keys)
    wiki_char_panels = build_wiki_char_panels_html(parts, visible_tab_keys, False)

    slug_final = (slug or slugify_page_title(title)).strip().lower()
    if not slug_final:
        slug_final = "page"

    tree_map = load_title_to_category_path(root)
    if category_path is not None:
        cat_used = category_path.strip().strip("/")
        if not cat_used:
            cat_used = category_path_for_title(title, tree_map)
    else:
        cat_used = category_path_for_title(title, tree_map)

    title_esc = html.escape(title)
    tree_root = load_tree(root)
    wiki_breadcrumb_block = build_content_mirror_breadcrumb_nav_html(
        cat_used, title, tree=tree_root
    )
    extra_head = f'    <meta name="wiki-page-title" content="{html.escape(title, quote=True)}" />\n'

    page = TEMPLATE.format(
        display=title_esc,
        extra_head=extra_head,
        wiki_breadcrumb_block=wiki_breadcrumb_block,
        hero_card=hero_card,
        wiki_char_split_cls=split_cls,
        toc_sidebar=toc_sidebar,
        toc_bar="",
        wiki_char_tabs=wiki_char_tabs,
        wiki_char_panels=wiki_char_panels,
    )
    page = dedupe_toc_ids_in_full_page(page)

    article_dir = pages_article_dir(root, cat_used, slug_final)
    out_path = article_dir / "index.html"
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(page, encoding="utf-8")
    if not quiet:
        print(f"Wrote {out_path} ({len(page)} bytes)", file=sys.stderr)
    return out_path, slug_final, title, cat_used


def main() -> None:
    ap = argparse.ArgumentParser(description="Import one Fandom wiki article to pages/<slug>/.")
    ap.add_argument("title", nargs="?", help="Wiki page title (e.g. Season 15: Crystalized)")
    ap.add_argument("--slug", help="Override URL slug under /pages/")
    ap.add_argument(
        "--category-path",
        help="Category slug path (e.g. content/abilities/elements). Default: from category tree.",
    )
    ap.add_argument("--root", type=Path, default=ROOT)
    args = ap.parse_args()
    if not args.title:
        ap.error("title required")
    import_wiki_page(
        args.title.strip(),
        slug=args.slug,
        category_path=args.category_path,
        root=args.root.resolve(),
    )


if __name__ == "__main__":
    main()
