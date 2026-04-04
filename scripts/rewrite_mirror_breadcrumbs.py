#!/usr/bin/env python3
"""
Rewrite <nav class="wiki-char-breadcrumb"> on mirrored wiki pages (pages/**/index.html).

Uses filesystem path under pages/ for the category slug trail and <meta name="wiki-page-title">
for the article title. Does not touch characters/*.
"""

from __future__ import annotations

import argparse
import html as html_module
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))

from wiki_tree_category_paths import build_content_mirror_breadcrumb_nav_html, load_tree  # noqa: E402

META_TITLE_RE = re.compile(
    r'<meta\s+name="wiki-page-title"\s+content="([^"]*)"\s*/>',
    re.I,
)
CRUMB_BLOCK_RE = re.compile(
    r'[ \t]*<nav class="wiki-char-breadcrumb"[^>]*>.*?</nav>\s*\n\s*<h1 class="visually-hidden">.*?</h1>',
    re.DOTALL,
)


def category_path_from_pages_index(path: Path, pages_root: Path) -> str | None:
    try:
        rel = path.parent.relative_to(pages_root)
    except ValueError:
        return None
    parts = list(rel.parts)
    if len(parts) < 2:
        return None
    return "/".join(parts[:-1])


def main() -> None:
    ap = argparse.ArgumentParser(description="Rewrite breadcrumbs on pages/**/index.html")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = args.root.resolve()
    pages_root = root / "pages"
    if not pages_root.is_dir():
        print("No pages/ directory", file=sys.stderr)
        sys.exit(1)

    tree = load_tree(root)
    updated = 0
    skipped = 0
    for html_path in sorted(pages_root.rglob("index.html")):
        text = html_path.read_text(encoding="utf-8")
        if "wiki-char-breadcrumb" not in text or "wiki-page-title" not in text:
            skipped += 1
            continue
        m = META_TITLE_RE.search(text)
        if not m:
            skipped += 1
            continue
        title_plain = html_module.unescape(m.group(1))
        cat = category_path_from_pages_index(html_path, pages_root)
        if not cat:
            skipped += 1
            continue
        new_block = build_content_mirror_breadcrumb_nav_html(cat, title_plain, tree=tree)
        new_text, n = CRUMB_BLOCK_RE.subn(new_block, text, count=1)
        if n != 1:
            skipped += 1
            continue
        if new_text != text:
            updated += 1
            if not args.dry_run:
                html_path.write_text(new_text, encoding="utf-8")

    print(f"Updated {updated} files, skipped {skipped}", file=sys.stderr)


if __name__ == "__main__":
    main()
