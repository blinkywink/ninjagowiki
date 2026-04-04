#!/usr/bin/env python3
"""
Rewrite href="/pages/<slug>" → manifest href when articles moved under the category tree.

Skips URLs that already have a nested path (/pages/content/...).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WIKI_PAGES_JSON = ROOT / "assets" / "data" / "wiki_pages.json"

A_PAGES_HREF_RE = re.compile(
    r'(?P<before>href\s*=\s*)(?P<q>["\'])(?P<url>/pages/(?P<rest>[^"\']+))(?P=q)',
    re.IGNORECASE,
)


def load_slug_to_href(root: Path) -> dict[str, str]:
    p = root / "assets" / "data" / "wiki_pages.json"
    with open(p, encoding="utf-8") as f:
        data = json.load(f)
    out: dict[str, str] = {}
    for row in data.get("pages") or []:
        slug = (row.get("slug") or "").strip()
        href = (row.get("href") or "").strip()
        if slug and href.startswith("/pages/"):
            out[slug] = href
    return out


def rewrite_html(html: str, slug_to_href: dict[str, str]) -> tuple[str, int]:
    n = 0

    def repl(m: re.Match[str]) -> str:
        nonlocal n
        rest = m.group("rest").strip("/")
        if "/" in rest:
            return m.group(0)
        slug = rest
        new_href = slug_to_href.get(slug)
        if not new_href:
            return m.group(0)
        old_url = m.group("url")
        if new_href == old_url or new_href.rstrip("/") == old_url.rstrip("/"):
            return m.group(0)
        n += 1
        return f'{m.group("before")}{m.group("q")}{new_href}{m.group("q")}'

    new_html = A_PAGES_HREF_RE.sub(repl, html)
    return new_html, n


def iter_html_files(root: Path, extra_ignore: list[str]) -> list[Path]:
    ignore_parts = {".git", *extra_ignore}
    out: list[Path] = []
    for p in root.rglob("*.html"):
        try:
            rel = p.relative_to(root)
        except ValueError:
            continue
        if any(part in ignore_parts for part in rel.parts):
            continue
        out.append(p)
    return sorted(out)


def main() -> None:
    ap = argparse.ArgumentParser(description="Fix flat /pages/slug links after tree migration.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--apply", action="store_true")
    ap.add_argument("--ignore-dir", action="append", default=[])
    args = ap.parse_args()
    root = args.root.resolve()

    slug_to_href = load_slug_to_href(root)
    files = iter_html_files(root, args.ignore_dir)
    total = 0
    changed = 0
    for path in files:
        text = path.read_text(encoding="utf-8")
        new_text, n = rewrite_html(text, slug_to_href)
        total += n
        if n:
            changed += 1
            if args.apply:
                path.write_text(new_text, encoding="utf-8")

    mode = "WROTE" if args.apply else "DRY-RUN"
    print(f"{mode}: {total} href(s) in {changed} file(s); scanned {len(files)} html.", file=sys.stderr)
    if not args.apply and total:
        print("Re-run with --apply to save.", file=sys.stderr)


if __name__ == "__main__":
    main()
