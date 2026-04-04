#!/usr/bin/env python3
"""
Rewrite:
1) <a href="https://ninjago.fandom.com/wiki/..."> → /characters/<slug> when we have that
   character page (from characters.json wikiUrl + characters/<slug>/index.html).
2) <a href="/characters#slug"> → /characters/slug (homepage used to send people to the
   browse page + hash instead of the article).

Uses assets/data/characters.json for wiki URLs, merged with assets/data/site_routes.json
(/pages/… routes from wiki_pages.json) so generic mirrored articles link locally too.
Hash fix does not require a manifest row beyond the slug matching your URL scheme.

Default is dry-run (report only). Pass --apply to overwrite files.

Does not run automatically — invoke when character imports are complete:

  python3 scripts/rewrite_fandom_character_links.py
  python3 scripts/rewrite_fandom_character_links.py --apply
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from urllib.parse import unquote, urlparse

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CHARACTERS_JSON = ROOT / "assets" / "data" / "characters.json"
SITE_ROUTES_JSON = ROOT / "assets" / "data" / "site_routes.json"

WIKI_HOST = "ninjago.fandom.com"

# Opening <a ... href="..."> — href value in group "url".
A_HREF_RE = re.compile(
    r'(?P<before><a\s[^>]*\bhref\s*=\s*)(?P<quote>["\'])(?P<url>[^"\']*)(?P=quote)',
    re.IGNORECASE | re.DOTALL,
)

# /characters#cole → /characters/cole (trending list on index.html)
CHARACTERS_HASH_HREF_RE = re.compile(
    r'(?P<before><a\s[^>]*\bhref\s*=\s*)(?P<q>["\'])/characters#(?P<slug>[a-z0-9-]+)(?P=q)',
    re.IGNORECASE | re.DOTALL,
)

SKIP_PATH_PREFIXES = (
    "/wiki/special:",
    "/wiki/file:",
    "/wiki/category:",
    "/wiki/template:",
    "/wiki/user:",
    "/wiki/talk:",
    "/wiki/mediawiki:",
    "/wiki/help:",
    "/wiki/ninjago:",
)


def load_characters(root: Path) -> list[dict]:
    with open(root / "assets" / "data" / "characters.json", encoding="utf-8") as f:
        data = json.load(f)
    return list(data.get("characters") or [])


def local_character_page(root: Path, slug: str) -> Path:
    return root / "characters" / slug / "index.html"


def wiki_path_from_url(wiki_url: str) -> str | None:
    """Return decoded path like '/wiki/Lloyd' (no trailing slash), or None."""
    u = (wiki_url or "").strip()
    if not u:
        return None
    p = urlparse(u)
    path = unquote(p.path).rstrip("/")
    if "/wiki/" not in path:
        return None
    return path


def should_skip_wiki_path(path_lower: str) -> bool:
    if not path_lower.startswith("/wiki/"):
        return True
    return any(path_lower.startswith(p) for p in SKIP_PATH_PREFIXES)


def build_wiki_path_to_local(root: Path, characters: list[dict]) -> dict[str, str]:
    """
    Map normalized wiki pathname (lowercase) -> /characters/slug.
    Only entries with an existing characters/<slug>/index.html.
    """
    out: dict[str, str] = {}
    for c in characters:
        slug = (c.get("slug") or "").strip()
        if not slug:
            continue
        if not local_character_page(root, slug).is_file():
            continue
        wiki_url = (c.get("wikiUrl") or "").strip()
        path = wiki_path_from_url(wiki_url)
        if not path:
            continue
        pl = path.lower()
        if should_skip_wiki_path(pl):
            continue
        local_href = f"/characters/{slug}"
        out[pl] = local_href
        # Underscore vs space in URLs
        if "_" in pl:
            out[pl.replace("_", " ")] = local_href
        if " " in pl:
            out[pl.replace(" ", "_")] = local_href
    return out


def parse_href_for_lookup(href: str) -> tuple[str | None, str, str]:
    """
    Return (lookup_path_lowercase, fragment, tail_query) for a wiki article URL.
    lookup_path is '/wiki/Title' form or None if not a ninjago wiki article link.
    fragment and query are preserved for rebuilding (query dropped on rewrite to local).
    """
    raw = (href or "").strip()
    if not raw or raw.startswith("#"):
        return None, "", ""

    frag = ""
    if "#" in raw:
        raw, frag = raw.split("#", 1)

    p = urlparse(raw)
    query = p.query

    host = (p.netloc or "").lower()
    path = unquote(p.path)

    # Protocol-relative
    if raw.startswith("//"):
        p2 = urlparse("https:" + raw)
        host = (p2.netloc or "").lower()
        path = unquote(p2.path)

    # Site-relative on our domain (unlikely for fandom)
    if not host and path.startswith("//"):
        p2 = urlparse("https:" + path)
        host = (p2.netloc or "").lower()
        path = unquote(p2.path)

    if WIKI_HOST not in host and host != "":
        # Relative /wiki/... with no host
        if not host and path.startswith("/wiki/"):
            pass
        else:
            return None, frag, query

    path = path.rstrip("/")
    pl = path.lower()
    if not pl.startswith("/wiki/") or should_skip_wiki_path(pl):
        return None, frag, query

    return pl, frag, query


def local_href_for_url(href: str, path_to_local: dict[str, str]) -> str | None:
    pl, frag, _query = parse_href_for_lookup(href)
    if pl is None:
        return None

    local = path_to_local.get(pl)
    if local is None and "_" in pl:
        local = path_to_local.get(pl.replace("_", " "))
    if local is None and " " in pl:
        local = path_to_local.get(pl.replace(" ", "_"))

    if not local:
        return None

    if frag:
        local = f"{local}#{frag}"
    return local


def rewrite_html_a_hrefs(html: str, path_to_local: dict[str, str]) -> tuple[str, int]:
    """Return (new_html, replacement_count)."""

    def repl(m: re.Match[str]) -> str:
        url = m.group("url")
        new_url = local_href_for_url(url, path_to_local)
        if new_url is None or new_url == url:
            return m.group(0)
        q = m.group("quote")
        return f'{m.group("before")}{q}{new_url}{q}'

    new_html, n = A_HREF_RE.subn(repl, html)
    return new_html, n


def rewrite_characters_hash_hrefs(html: str) -> tuple[str, int]:
    """href="/characters#slug" → href="/characters/slug"."""

    def repl(m: re.Match[str]) -> str:
        return (
            f'{m.group("before")}{m.group("q")}/characters/{m.group("slug")}{m.group("q")}'
        )

    return CHARACTERS_HASH_HREF_RE.subn(repl, html)


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
    ap = argparse.ArgumentParser(
        description="Rewrite Fandom character wiki links to local /characters/<slug> where pages exist."
    )
    ap.add_argument(
        "--root",
        type=Path,
        default=ROOT,
        help=f"Site root (default: {ROOT})",
    )
    ap.add_argument(
        "--apply",
        action="store_true",
        help="Write changed files (default: dry-run only).",
    )
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print every rewritten href.",
    )
    ap.add_argument(
        "--ignore-dir",
        action="append",
        default=[],
        metavar="NAME",
        help="Extra directory name under root to skip (repeatable).",
    )
    args = ap.parse_args()
    root: Path = args.root.resolve()

    if not CHARACTERS_JSON.is_file():
        print(f"Missing {CHARACTERS_JSON}", file=sys.stderr)
        sys.exit(1)

    characters = load_characters(root)
    path_to_local = build_wiki_path_to_local(root, characters)
    if SITE_ROUTES_JSON.is_file():
        with open(SITE_ROUTES_JSON, encoding="utf-8") as f:
            sr = json.load(f)
        for k, v in (sr.get("wikiPathToHref") or {}).items():
            path_to_local.setdefault(k, v)
    print(
        f"Loaded {len(characters)} character manifest rows; "
        f"{len(path_to_local)} wiki paths map to local pages (characters + site_routes).",
        file=sys.stderr,
    )

    html_files = iter_html_files(root, args.ignore_dir)
    total_fandom = 0
    total_hash = 0
    files_changed = 0

    for path in html_files:
        text = path.read_text(encoding="utf-8")
        new_text, n1 = rewrite_html_a_hrefs(text, path_to_local)
        new_text, n2 = rewrite_characters_hash_hrefs(new_text)
        n = n1 + n2
        if n == 0:
            continue
        total_fandom += n1
        total_hash += n2
        files_changed += 1
        if args.verbose:
            for m in A_HREF_RE.finditer(text):
                old_u = m.group("url")
                new_u = local_href_for_url(old_u, path_to_local)
                if new_u and new_u != old_u:
                    print(f"{path.relative_to(root)}: {old_u!r} -> {new_u!r}")
            for m in CHARACTERS_HASH_HREF_RE.finditer(text):
                print(
                    f"{path.relative_to(root)}: '/characters#{m.group('slug')}' -> '/characters/{m.group('slug')}'"
                )
        if args.apply:
            path.write_text(new_text, encoding="utf-8")

    mode = "WROTE" if args.apply else "DRY-RUN"
    print(
        f"{mode}: fandom→local {total_fandom}, /characters#→/characters/ {total_hash} "
        f"({total_fandom + total_hash} total) in {files_changed} file(s); "
        f"scanned {len(html_files)} html.",
        file=sys.stderr,
    )
    if not args.apply and (total_fandom + total_hash):
        print("Re-run with --apply to save changes.", file=sys.stderr)


if __name__ == "__main__":
    main()
