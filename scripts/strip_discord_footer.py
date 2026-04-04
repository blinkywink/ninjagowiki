#!/usr/bin/env python3
"""Remove Discord footer link from all HTML files under the site root."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
# Match <a …footer-link--discord…>…</a> including nested SVG (multiline)
DISCORD_ANCHOR_RE = re.compile(
    r"\s*<a\b[^>]*\bfooter-link--discord\b[^>]*>.*?</a>\s*",
    re.DOTALL | re.IGNORECASE,
)


def main() -> None:
    n_files = 0
    for path in sorted(ROOT.rglob("*.html")):
        text = path.read_text(encoding="utf-8")
        if "footer-link--discord" not in text:
            continue
        new = DISCORD_ANCHOR_RE.sub("\n", text)
        if new != text:
            path.write_text(new, encoding="utf-8")
            n_files += 1
    print(f"Updated {n_files} HTML files (Discord footer removed).", file=sys.stderr)


if __name__ == "__main__":
    main()
