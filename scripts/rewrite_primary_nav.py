#!/usr/bin/env python3
"""
Normalize <nav class="nav" aria-label="Primary"> across all HTML files.

Default links (order):
  Characters, Episodes, Timeline, Weapons, Sets, Media, Trivia, All Pages

trivia/index.html gets aria-current on Trivia; all-pages/index.html on All Pages.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent

NAV_RE = re.compile(
    r'^[ \t]*<nav\s+class="nav"\s+aria-label="Primary">\s*.*?\s*</nav>',
    re.DOTALL | re.IGNORECASE | re.MULTILINE,
)

TIMELINE_HREF = "/pages/content/year/2011/pilot-episodes/timeline"
TRIVIA_LINK = (
    '<a href="/trivia" class="nav-link--featured">Trivia '
    '<span class="nav-badge">New</span></a>'
)
TRIVIA_CURRENT = (
    '<a href="/trivia" aria-current="page" class="nav-link--featured">Trivia '
    '<span class="nav-badge">New</span></a>'
)

STANDARD_NAV = f"""        <nav class="nav" aria-label="Primary">
          <a href="/characters">Characters</a>
          <a href="/episodes">Episodes</a>
          <a href="{TIMELINE_HREF}">Timeline</a>
          <a href="/weapons">Weapons</a>
          <a href="/sets">Sets</a>
          <a href="/media">Media</a>
          {TRIVIA_LINK}
          <a href="/all-pages">All Pages</a>
        </nav>"""

ALL_PAGES_NAV = f"""        <nav class="nav" aria-label="Primary">
          <a href="/characters">Characters</a>
          <a href="/episodes">Episodes</a>
          <a href="{TIMELINE_HREF}">Timeline</a>
          <a href="/weapons">Weapons</a>
          <a href="/sets">Sets</a>
          <a href="/media">Media</a>
          {TRIVIA_LINK}
          <a href="/all-pages" aria-current="page">All Pages</a>
        </nav>"""

TRIVIA_NAV = f"""        <nav class="nav" aria-label="Primary">
          <a href="/characters">Characters</a>
          <a href="/episodes">Episodes</a>
          <a href="{TIMELINE_HREF}">Timeline</a>
          <a href="/weapons">Weapons</a>
          <a href="/sets">Sets</a>
          <a href="/media">Media</a>
          {TRIVIA_CURRENT}
          <a href="/all-pages">All Pages</a>
        </nav>"""


def iter_html(root: Path) -> list[Path]:
    ignore = {".git"}
    out: list[Path] = []
    for p in root.rglob("*.html"):
        if any(part in ignore for part in p.relative_to(root).parts):
            continue
        out.append(p)
    return sorted(out)


def nav_for_path(rel: Path) -> str:
    posix = rel.as_posix()
    if posix == "all-pages/index.html":
        return ALL_PAGES_NAV
    if posix == "trivia/index.html":
        return TRIVIA_NAV
    return STANDARD_NAV


def main() -> None:
    ap = argparse.ArgumentParser(description="Rewrite primary site header nav.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    root = args.root.resolve()

    changed = 0
    total = 0
    for path in iter_html(root):
        text = path.read_text(encoding="utf-8")
        if not NAV_RE.search(text):
            continue
        rel = path.relative_to(root)
        replacement = nav_for_path(rel)
        new_text, n = NAV_RE.subn(replacement, text, count=1)
        if n == 0:
            continue
        total += 1
        if new_text != text:
            changed += 1
            if args.apply:
                path.write_text(new_text, encoding="utf-8")

    mode = "WROTE" if args.apply else "DRY-RUN"
    print(f"{mode}: updated {changed} file(s) with primary nav ({total} had matching nav).", file=sys.stderr)


if __name__ == "__main__":
    main()
