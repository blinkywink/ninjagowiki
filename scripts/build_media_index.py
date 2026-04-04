#!/usr/bin/env python3
"""
Build assets/data/media_index.json from wiki_pages.json (magazines) and the Fandom
category tree (Category:Albums, Category:Songs under content).

Browse groups: Magazines → Albums → Songs. Rows deduped by href across groups
(first wins). Only mirrored pages on disk are included.
"""

from __future__ import annotations

import json
import re
import sys
from collections import defaultdict
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from search_snippet_extract import thumb_from_mirror_html  # noqa: E402

WIKI_PAGES = ROOT / "assets/data/wiki_pages.json"
WIKI_SEARCH = ROOT / "assets/data/wiki_search_index.json"
TREE_JSON = ROOT / "assets/data/fandom_content_category_tree.json"
OUT = ROOT / "assets/data/media_index.json"

GENERIC_THUMBS = frozenset(
    {
        "/assets/hero.png",
        "/assets/hero-mobile.png",
        "",
    }
)

SKIP_TREE_PAGE_LOWER = frozenset(
    {
        "4+",
    }
)


def fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_key(s: str) -> str:
    return (s or "").replace("\u2019", "'").replace("\u2018", "'").strip().lower()


def upscale_wikia_thumb(url: str) -> str:
    if not url or "scale-to-width-down/" not in url:
        return url
    return re.sub(r"scale-to-width-down/\d+", "scale-to-width-down/450", url, count=1)


def load_thumb_by_href() -> dict[str, str]:
    if not WIKI_SEARCH.is_file():
        return {}
    try:
        data = json.loads(WIKI_SEARCH.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    out: dict[str, str] = {}
    for p in data.get("pages") or []:
        h = (p.get("href") or "").split("?")[0].rstrip("/")
        th = (p.get("thumb") or "").strip()
        if not h or not th or th in GENERIC_THUMBS:
            continue
        out[h] = th
        out.setdefault(h.rstrip("/"), th)
        out.setdefault(h + "/", th)
    return out


def href_to_mirror_path(href: str) -> Path | None:
    h = (href or "").split("?")[0].strip()
    if not h.startswith("/pages/"):
        return None
    rel = h[len("/pages/") :].strip("/").split("/")
    if not rel or not rel[0]:
        return None
    return ROOT.joinpath("pages", *rel, "index.html")


def read_mirror_html(path: Path, max_bytes: int = 900_000) -> str:
    try:
        raw = path.read_bytes()
    except OSError:
        return ""
    if len(raw) > max_bytes:
        raw = raw[:max_bytes]
    return raw.decode("utf-8", errors="ignore")


def find_tree_node(tree_root: dict, title: str) -> dict | None:
    def walk(n: dict) -> dict | None:
        if (n.get("title") or "") == title:
            return n
        for ch in n.get("children") or []:
            r = walk(ch)
            if r is not None:
                return r
        return None

    return walk(tree_root)


def collect_titles_for_group(root_node: dict) -> list[str]:
    seen_fold: set[str] = set()
    out: list[str] = []

    def walk(n: dict) -> None:
        for raw in n.get("directPages") or []:
            raw = (raw or "").strip()
            if not raw:
                continue
            f = fold(raw)
            if f in seen_fold:
                continue
            seen_fold.add(f)
            out.append(raw)
        for ch in n.get("children") or []:
            if ch.get("duplicate"):
                continue
            walk(ch)

    walk(root_node)
    return out


def skip_song_tree_title(raw: str) -> bool:
    s = raw.strip()
    if not s:
        return True
    low = s.lower()
    if low in SKIP_TREE_PAGE_LOWER:
        return True
    if low.startswith("user:") or low.startswith("template:"):
        return True
    if low.startswith("ninjago wiki:"):
        return True
    if re.search(r" \(sets\)$", low):
        return True
    return False


def build_wiki_title_index(pages: list[dict]) -> dict[str, list[dict]]:
    by_norm: dict[str, list[dict]] = defaultdict(list)
    for p in pages:
        for k in (p.get("wikiTitle"), p.get("display")):
            if not (k and str(k).strip()):
                continue
            by_norm[norm_key(k)].append(p)
    return by_norm


def mirror_exists(p: dict) -> bool:
    path = href_to_mirror_path(p.get("href") or "")
    return bool(path and path.is_file())


def resolve_tree_title(raw_title: str, by_norm: dict[str, list[dict]]) -> dict | None:
    nk = norm_key(raw_title)
    cands = by_norm.get(nk, [])
    if not cands:
        return None
    by_href: dict[str, dict] = {}
    for p in cands:
        h = (p.get("href") or "").split("?")[0].rstrip("/")
        if h:
            by_href.setdefault(h, p)
    on_disk = [p for p in by_href.values() if mirror_exists(p)]
    if not on_disk:
        return None

    def sort_key(p: dict) -> tuple:
        cp = (p.get("categoryPath") or "").lower()
        pref = 1 if any(x in cp for x in ("song", "music", "magazine", "album")) else 0
        return (pref, -len(cp))

    on_disk.sort(key=sort_key, reverse=True)
    return on_disk[0]


def is_excluded_manifest(p: dict) -> bool:
    slug = (p.get("slug") or "").lower()
    disp = (p.get("display") or "").lower()
    href = (p.get("href") or "").lower()
    wiki_u = (p.get("wikiUrl") or "").lower()
    if disp.startswith("user:") or "/wiki/user:" in wiki_u:
        return True
    if "transcript" in slug or slug.endswith("gallery"):
        return True
    if "disambiguation" in disp:
        return True
    if "/transcript" in href:
        return True
    return False


def is_magazine_manifest_row(p: dict) -> bool:
    slug = (p.get("slug") or "").lower()
    href = (p.get("href") or "").lower()
    cp = (p.get("categoryPath") or "").lower()
    return "magazine" in slug or "magazine" in href or "magazine" in cp


def group_search_blob(group_slug: str, group_title: str) -> str:
    t = (group_title or "").strip()
    bits: list[str] = [t, group_slug.replace("-", " ").replace("__", " ")]
    if t:
        bits.append(t.replace("'", " ").replace("’", " "))
    if group_slug == "magazines":
        bits.extend(["magazine", "mini comic", "legacy", "hero magazine", "polybag"])
    elif group_slug == "albums":
        bits.extend(["album", "soundtrack", "score", "music cd", "ost"])
    elif group_slug == "songs":
        bits.extend(
            [
                "song",
                "songs",
                "music",
                "lyrics",
                "theme",
                "whip",
                "weekend whip",
                "ninjago music",
            ]
        )
    seen: set[str] = set()
    out: list[str] = []
    for x in bits:
        x = (x or "").strip()
        if not x:
            continue
        f = fold(x)
        if f and f not in seen:
            seen.add(f)
            out.append(x)
    return " ".join(out)


def media_row(
    p: dict,
    thumbs: dict[str, str],
    group_title: str,
    group_slug: str,
    html_cache: dict[str, str],
) -> dict:
    href = (p.get("href") or "").split("?")[0].rstrip("/")
    display = (p.get("display") or "").strip() or "Media"
    slug = p.get("slug") or ""
    kw = (p.get("keywords") or "").strip()
    wiki_t = (p.get("wikiTitle") or "").strip()

    path = href_to_mirror_path(href)
    html = ""
    if path:
        ck = str(path)
        if ck not in html_cache:
            html_cache[ck] = read_mirror_html(path) if path.is_file() else ""
        html = html_cache[ck]

    th = (
        thumbs.get(href)
        or thumbs.get(href + "/")
        or (p.get("thumb") or "").strip()
    )
    if th in GENERIC_THUMBS:
        th = ""
    if not th and html:
        th = (thumb_from_mirror_html(html, None) or "").strip()
    th = upscale_wikia_thumb(th)
    if th in GENERIC_THUMBS:
        th = ""

    gblob = group_search_blob(group_slug, group_title)
    flt = f"{kw} {display} {wiki_t} {gblob}".strip()

    return {
        "display": display,
        "href": href,
        "slug": slug,
        "filter": flt,
        "img": th,
    }


def main() -> None:
    if not TREE_JSON.is_file():
        print(f"Missing {TREE_JSON}", file=sys.stderr)
        sys.exit(1)

    tree_data = json.loads(TREE_JSON.read_text(encoding="utf-8"))
    tree_root = tree_data.get("tree") or {}
    songs_node = find_tree_node(tree_root, "Category:Songs")
    albums_node = find_tree_node(tree_root, "Category:Albums")
    if not songs_node:
        print("Category:Songs not found in tree.", file=sys.stderr)
        sys.exit(1)
    if not albums_node:
        print("Category:Albums not found in tree.", file=sys.stderr)
        sys.exit(1)

    pages = json.loads(WIKI_PAGES.read_text(encoding="utf-8")).get("pages") or []
    by_norm = build_wiki_title_index(pages)
    thumbs = load_thumb_by_href()
    html_cache: dict[str, str] = {}
    seen_href: set[str] = set()
    groups_out: list[dict] = []

    # Magazines from manifest (paths/slugs mentioning magazine)
    mag_rows: list[dict] = []
    for p in pages:
        if not is_magazine_manifest_row(p):
            continue
        if is_excluded_manifest(p) or not mirror_exists(p):
            continue
        href = (p.get("href") or "").split("?")[0].rstrip("/")
        if href in seen_href:
            continue
        mag_rows.append(
            media_row(p, thumbs, "Magazines", "magazines", html_cache),
        )
        seen_href.add(href)
    mag_rows.sort(key=lambda r: (r.get("display") or "").lower())
    if mag_rows:
        groups_out.append(
            {
                "id": "magazines",
                "title": "Magazines",
                "groupKey": "magazines",
                "groupHref": None,
                "sets": mag_rows,
            }
        )

    def add_tree_group(node: dict, title: str, slug: str) -> None:
        nonlocal seen_href
        built: list[dict] = []
        for raw_title in collect_titles_for_group(node):
            if skip_song_tree_title(raw_title):
                continue
            p = resolve_tree_title(raw_title, by_norm)
            if not p or is_excluded_manifest(p):
                continue
            href = (p.get("href") or "").split("?")[0].rstrip("/")
            if href in seen_href:
                continue
            built.append(media_row(p, thumbs, title, slug, html_cache))
            seen_href.add(href)
        built.sort(key=lambda r: (r.get("display") or "").lower())
        if built:
            groups_out.append(
                {
                    "id": slug,
                    "title": title,
                    "groupKey": slug,
                    "groupHref": None,
                    "sets": built,
                }
            )

    add_tree_group(albums_node, "Albums", "albums")
    add_tree_group(songs_node, "Songs", "songs")

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "v": 1,
        "source": "wiki_pages.json (magazine*) + fandom tree Category:Albums, Category:Songs",
        "groups": groups_out,
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n = sum(len(g["sets"]) for g in groups_out)
    print(f"Wrote {OUT} — {len(groups_out)} groups, {n} items (mirrored only)", file=sys.stderr)


if __name__ == "__main__":
    main()
