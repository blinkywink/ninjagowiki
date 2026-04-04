#!/usr/bin/env python3
"""
Build assets/data/sets_index.json from the Fandom category tree + wiki_pages.json.

Uses Category:Content → Category:Sets in assets/data/fandom_content_category_tree.json
(the same organization as the wiki: year set lines, polybag years, keychains, etc.),
not categoryPath in wiki_pages (many sets are miscategorized under spinners, abilities, …).

Each group is a direct child of Category:Sets; Category:Polybags is expanded into its
year subcategories only (the parent Polybags node also lists every polybag — we skip that
flat list to avoid one giant bucket).

Only includes rows whose mirrored page exists on disk.
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
OUT = ROOT / "assets/data/sets_index.json"

GENERIC_THUMBS = frozenset(
    {
        "/assets/hero.png",
        "/assets/hero-mobile.png",
        "",
    }
)

# Page names listed on category pages that are not set articles.
SKIP_TREE_PAGE_LOWER = frozenset(
    {
        "ninjago (sets)",
        "spinners",
        "spinner crowns",
        "booster packs",
        "serpentine vehicles",
        "airjitzu flyers",
        "ninjago: legacy",
        "4+",
    }
)


def fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def norm_key(s: str) -> str:
    t = (s or "").replace("\u2019", "'").replace("\u2018", "'").strip().lower()
    return t


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


def find_category_sets_node(tree_root: dict) -> dict | None:
    """Depth-first: first node with title Category:Sets."""

    def walk(n: dict) -> dict | None:
        if (n.get("title") or "") == "Category:Sets":
            return n
        for ch in n.get("children") or []:
            r = walk(ch)
            if r is not None:
                return r
        return None

    return walk(tree_root)


def iter_set_group_nodes(sets_category: dict):
    """One node per browse section: expand Polybags into year children only."""
    for child in sets_category.get("children") or []:
        title = child.get("title") or ""
        if title == "Category:Polybags":
            for sub in child.get("children") or []:
                if sub.get("duplicate"):
                    continue
                yield sub
        else:
            yield child


def collect_titles_for_group(root_node: dict) -> list[str]:
    """directPages + non-duplicate descendants (e.g. Booster Packs under 2012 sets)."""
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


def skip_tree_page_title(raw: str) -> bool:
    s = raw.strip()
    if not s:
        return True
    low = s.lower()
    if low in SKIP_TREE_PAGE_LOWER:
        return True
    if low.startswith("user:") or low.startswith("template:"):
        return True
    # Hub lines like "Dragon Masters (sets)" — not individual set articles
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
        cp = p.get("categoryPath") or ""
        pref = 2 if cp.startswith("content/sets/") else 0
        return (pref, -len(cp))

    on_disk.sort(key=sort_key, reverse=True)
    return on_disk[0]


def is_excluded_manifest(p: dict) -> bool:
    slug = (p.get("slug") or "").lower()
    disp = (p.get("display") or "").lower()
    href = (p.get("href") or "").lower()
    if "transcript" in slug or slug.endswith("gallery"):
        return True
    if "disambiguation" in disp:
        return True
    if "/transcript" in href:
        return True
    return False


def primary_set_number(slug: str) -> int | None:
    m = re.match(r"^(\d{3,7})(?:-|$)", slug or "")
    if m:
        return int(m.group(1))
    return None


def set_search_codes(slug: str) -> list[str]:
    n = primary_set_number(slug)
    if n is None:
        return []
    s = str(n)
    return [s, f"set{s}", f"lego{s}"]


def group_search_blob(group_title: str, group_slug: str) -> str:
    t = (group_title or "").strip()
    bits: list[str] = [t, group_slug.replace("-", " ").replace("__", " ")]
    if t:
        bits.append(t.replace("'", " ").replace("’", " "))
    m = re.match(r"^(\d{4}) sets$", t, re.I)
    if m:
        y = m.group(1)
        bits.extend([y, f"{y}sets", f"sets{y}", f"lego{y}"])
    m2 = re.match(r"^(\d{4}) polybags$", t, re.I)
    if m2:
        y = m2.group(1)
        bits.extend(
            [
                "polybag",
                "polybags",
                y,
                f"{y}polybags",
                f"polybags{y}",
            ]
        )
    low = t.lower()
    if "keychain" in low:
        bits.extend(["keychain", "keychains", "key ring", "keyring"])
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


def group_sort_key(node: dict) -> tuple:
    title = node.get("title") or ""
    dn = (node.get("displayName") or node.get("slug") or "").lower()
    m = re.match(r"Category:(\d{4}) sets$", title)
    if m:
        return (0, -int(m.group(1)), dn)
    m2 = re.match(r"Category:(\d{4}) polybags$", title)
    if m2:
        return (1, -int(m2.group(1)), dn)
    return (2, 0, dn)


def set_row(
    p: dict,
    thumbs: dict[str, str],
    group_title: str,
    group_slug: str,
    html_cache: dict[str, str],
) -> dict:
    href = (p.get("href") or "").split("?")[0].rstrip("/")
    display = (p.get("display") or "").strip() or "Set"
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

    codes = set_search_codes(slug)
    code_str = " ".join(codes)
    gblob = group_search_blob(group_title, group_slug)
    flt = f"{kw} {display} {wiki_t} {code_str} {gblob}".strip()
    sort_n = primary_set_number(slug)

    return {
        "display": display,
        "href": href,
        "slug": slug,
        "filter": flt,
        "codes": codes,
        "img": th,
        "sortN": sort_n,
    }


def set_sort_key(meta: dict) -> tuple:
    n = meta.get("sortN")
    if n is not None:
        return (0, n, (meta.get("display") or "").lower())
    return (1, 0, (meta.get("display") or "").lower())


def main() -> None:
    if not TREE_JSON.is_file():
        print(f"Missing {TREE_JSON}", file=sys.stderr)
        sys.exit(1)

    tree_data = json.loads(TREE_JSON.read_text(encoding="utf-8"))
    tree_root = tree_data.get("tree") or {}
    sets_cat = find_category_sets_node(tree_root)
    if not sets_cat:
        print("Category:Sets not found in tree.", file=sys.stderr)
        sys.exit(1)

    pages = json.loads(WIKI_PAGES.read_text(encoding="utf-8")).get("pages") or []
    by_norm = build_wiki_title_index(pages)
    thumbs = load_thumb_by_href()
    html_cache: dict[str, str] = {}

    group_nodes = list(iter_set_group_nodes(sets_cat))
    group_nodes.sort(key=group_sort_key)

    groups_out: list[dict] = []
    for gn in group_nodes:
        g_slug = gn.get("slug") or fold(gn.get("displayName") or "sets")
        g_title = gn.get("displayName") or g_slug.replace("-", " ").title()
        titles = collect_titles_for_group(gn)
        built: list[dict] = []
        for raw_title in titles:
            if skip_tree_page_title(raw_title):
                continue
            p = resolve_tree_title(raw_title, by_norm)
            if not p or is_excluded_manifest(p):
                continue
            built.append(set_row(p, thumbs, g_title, g_slug, html_cache))
        built.sort(key=set_sort_key)
        for b in built:
            b.pop("sortN", None)
        if not built:
            continue
        gid = g_slug.replace("/", "__")
        groups_out.append(
            {
                "id": gid,
                "title": g_title,
                "groupKey": g_slug,
                "groupHref": None,
                "sets": built,
            }
        )

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {"v": 2, "source": "fandom_content_category_tree.json:Category:Sets", "groups": groups_out}
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    n_sets = sum(len(g["sets"]) for g in groups_out)
    print(f"Wrote {OUT} — {len(groups_out)} groups, {n_sets} sets (mirrored only)", file=sys.stderr)


if __name__ == "__main__":
    main()
