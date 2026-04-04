#!/usr/bin/env python3
"""
Build assets/data/episodes_index.json from wiki_pages.json.

- Any category path containing episodes-of-* (main show, mini-series, mini-movies) + specials.
- Pilot episodes (4) under content/year/2011/pilot-episodes.
- Wu's Teas shorts (content/mini-movies/wus-teas/*), excluding year/hub pages.
- Thumbnails: wiki_search_index, then local mirror HTML (infobox image).
- Search: season/group titles and aliases on every row so searching a season name lists its episodes.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
sys.path.insert(0, str(SCRIPT_DIR))
from search_snippet_extract import thumb_from_mirror_html  # noqa: E402

WIKI_PAGES = ROOT / "assets/data/wiki_pages.json"
WIKI_SEARCH = ROOT / "assets/data/wiki_search_index.json"
OUT = ROOT / "assets/data/episodes_index.json"

GENERIC_THUMBS = frozenset(
    {
        "/assets/hero.png",
        "/assets/hero-mobile.png",
        "",
    }
)

SPECIALS_CP = "content/episodes/specials"
PILOT_CP = "content/year/2011/pilot-episodes"
WU_TEAS_CP_PREFIX = "content/mini-movies/wus-teas"
# Hub + year article — not individual shorts
WU_TEAS_EXCLUDE_SLUGS = frozenset({"2017", "wus-teas"})

# Broadcast order (pilot season).
PILOT_SLUGS: list[str] = [
    "way-of-the-ninja",
    "the-golden-weapon",
    "king-of-shadows",
    "weapons-of-destiny",
]


def fold(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", (s or "").lower())


def extract_episode_group_key(category_path: str) -> str | None:
    """Return group id e.g. episodes-of-seabound, or specials."""
    if not category_path:
        return None
    if category_path == SPECIALS_CP:
        return "specials"
    parts = [x for x in category_path.split("/") if x]
    for seg in parts:
        if seg.startswith("episodes-of-"):
            return seg
    return None


def is_excluded_episode(p: dict) -> bool:
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


def build_folder_to_main_season(pages: list[dict]) -> dict[str, tuple[str, str, str]]:
    folder_to_main: dict[str, tuple[str, str, str]] = {}
    season_disp = re.compile(r"^Season\s+\d+", re.I)
    for p in pages:
        cp = p.get("categoryPath") or ""
        if not cp.startswith("content/seasons/"):
            continue
        parts = [x for x in cp.split("/") if x]
        if len(parts) < 3:
            continue
        folder = parts[2]
        disp = p.get("display") or ""
        if not season_disp.match(disp):
            continue
        slug = (p.get("slug") or "").lower()
        if "soundtrack" in slug:
            continue
        prev = folder_to_main.get(folder)
        href = p.get("href") or ""
        if prev is None:
            folder_to_main[folder] = (href, disp, p.get("slug") or "")
        else:
            if (p.get("slug") or "").startswith("season-") and "soundtrack" not in (p.get("slug") or "").lower():
                folder_to_main[folder] = (href, disp, p.get("slug") or "")
    return folder_to_main


def slug_main_href(pages: list[dict], folder: str) -> tuple[str, str] | None:
    for p in pages:
        if (p.get("slug") or "") != folder:
            continue
        href = (p.get("href") or "").strip()
        disp = (p.get("display") or "").strip()
        if not href:
            continue
        return href, disp
    return None


def group_key_to_folder(group: str) -> str:
    if group == "specials":
        return "specials"
    if group.startswith("episodes-of-"):
        return group[len("episodes-of-") :]
    return group


def resolve_season_hub(
    pages: list[dict], folder_to_main: dict[str, tuple[str, str, str]], folder: str
) -> tuple[str | None, str]:
    if folder in folder_to_main:
        href, disp, _ = folder_to_main[folder]
        return href, disp
    sm = slug_main_href(pages, folder)
    if sm:
        return sm[0], sm[1]
    return None, folder.replace("-", " ").title()


def parse_infobox_season_episode(html: str) -> tuple[str | None, int | None, int | None]:
    """
    Returns (kind, season_num_or_none, episode_num).
    kind 'pilot' | 'num' | None
    """
    block = re.search(
        r'class="pi-navigation[^"]*"[^>]*>[\s\S]{0,800}?</nav>',
        html,
        re.I,
    )
    chunk = block.group(0) if block else html[:25_000]
    pm = re.search(r"Season\s+Pilot\s*,\s*Episode\s+(\d+)", chunk, re.I)
    if pm:
        return ("pilot", None, int(pm.group(1)))
    nm = re.search(r"Season\s+(\d+)\s*,\s*Episode\s+(\d+)", chunk, re.I)
    if nm:
        return ("num", int(nm.group(1)), int(nm.group(2)))
    return (None, None, None)


def build_search_codes(group_id: str, kind: str | None, snum: int | None, epnum: int | None) -> list[str]:
    if epnum is None:
        return []
    out: list[str] = []
    e2 = f"{epnum:02d}"
    e1 = str(epnum)

    if group_id == "pilot-episodes" or kind == "pilot":
        out += [
            f"s00e{e2}",
            f"s00e{e1}",
            f"s0e{e2}",
            f"s0e{e1}",
            f"s00ep{e2}",
            f"s00ep{e1}",
            f"pilot{e2}",
            f"pilot{e1}",
            f"pe{e2}",
            f"pe{e1}",
        ]
    elif "season-" in group_id and "dragons-rising" in group_id:
        m = re.search(r"season-(\d+)-dragons-rising", group_id)
        if m:
            dr = int(m.group(1))
            out += [
                f"dr{dr}e{e2}",
                f"dr{dr}e{e1}",
                f"drs{dr}e{e2}",
                f"dr{dr}x{e2}",
                f"dr{dr}ep{e2}",
            ]
    elif snum is not None:
        s2 = f"{snum:02d}"
        out += [
            f"s{s2}e{e2}",
            f"s{s2}e{e1}",
            f"s{snum}e{e2}",
            f"s{snum}e{e1}",
            f"s{s2}ep{e2}",
            f"s{s2}ep{e1}",
            f"s{snum}ep{e2}",
        ]
    # de-dupe preserve order
    seen: set[str] = set()
    uniq: list[str] = []
    for c in out:
        f = fold(c)
        if f and f not in seen:
            seen.add(f)
            uniq.append(c)
    return uniq


def group_search_blob(season_title: str, group_id: str) -> str:
    """Tokens so searching a season or arc name matches every episode in that group."""
    st = (season_title or "").strip()
    bits: list[str] = [st, group_id.replace("-", " ")]
    if st:
        bits.append(st.replace("'", " ").replace("’", " "))
    if group_id.startswith("episodes-of-"):
        tail = group_id[len("episodes-of-") :].replace("-", " ")
        bits.append(tail)
    m_season = re.search(r"Season\s+(\d+)", st, re.I)
    if m_season:
        n = m_season.group(1)
        bits.extend([f"season{n}", f"season {n}", f"s{n}", f"s{int(n):02d}"])
    if re.search(r"Dragons Rising", st, re.I):
        bits.append("dragons rising ninjago dragons rising")
        if m_season:
            bits.append(f"dragons rising season {m_season.group(1)}")
    if group_id == "pilot-episodes":
        bits.append("pilot episodes pilot season season zero")
    if group_id == "wus-teas" or ("wu" in st.lower() and "tea" in st.lower()):
        bits.append("wus teas wu teas master wu teas sensei wu teas")
    if "wyldfyre" in group_id.lower():
        bits.append("wyldfyre wyldfyres voice notes stories campaign")
    if "ninjago-reimagined" in group_id.lower():
        bits.append("ninjago reimagined re-imagined")
    return " ".join(x for x in bits if x and str(x).strip())


def sort_key_for_ep(meta: dict) -> tuple:
    return (
        meta.get("sortS", 999),
        meta.get("sortE", 999),
        (meta.get("display") or "").lower(),
    )


def season_sort_key(entry: dict) -> tuple:
    title = entry["title"]
    sid = entry["id"]
    if sid == "pilot-episodes":
        return (0, 0, title.lower())
    if re.search(r"Dragons Rising", title, re.I):
        m = re.search(r"Season\s+(\d+)", title, re.I)
        return (3, int(m.group(1)) if m else 99, title.lower())
    m = re.search(r"Season\s+(\d+)\s*:", title)
    if m:
        return (1, int(m.group(1)), title.lower())
    if sid == "specials":
        return (2, 0, title.lower())
    return (2, 1, title.lower())


def episode_row(
    p: dict,
    thumbs: dict[str, str],
    group_id: str,
    season_title: str,
    html_cache: dict[str, str],
) -> dict:
    href = (p.get("href") or "").split("?")[0].rstrip("/")
    display = (p.get("display") or "").strip() or "Episode"
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

    kind, snum, epnum = parse_infobox_season_episode(html) if html else (None, None, None)
    codes = build_search_codes(group_id, kind, snum, epnum)
    sort_s, sort_e = 999, 999
    if group_id == "pilot-episodes" and epnum is not None:
        sort_s, sort_e = 0, epnum
    elif "season-" in group_id and "dragons-rising" in group_id:
        m = re.search(r"season-(\d+)-dragons-rising", group_id)
        if m and epnum is not None:
            sort_s, sort_e = 100 + int(m.group(1)), epnum
    elif snum is not None and epnum is not None:
        sort_s, sort_e = snum, epnum

    code_str = " ".join(codes)
    gblob = group_search_blob(season_title, group_id)
    flt = f"{kw} {display} {wiki_t} {code_str} {gblob}".strip()

    return {
        "display": display,
        "href": href,
        "slug": slug,
        "filter": flt,
        "codes": codes,
        "img": th,
        "sortS": sort_s,
        "sortE": sort_e,
    }


def main() -> None:
    pages = json.loads(WIKI_PAGES.read_text(encoding="utf-8")).get("pages") or []
    folder_to_main = build_folder_to_main_season(pages)
    thumbs = load_thumb_by_href()

    groups: dict[str, list[dict]] = {}
    for p in pages:
        cp = p.get("categoryPath") or ""
        g = extract_episode_group_key(cp)
        if g is None:
            continue
        if g == "transcript" or g.endswith("-transcript"):
            continue
        if is_excluded_episode(p):
            continue
        groups.setdefault(g, []).append(p)

    # Wu's Teas (mini-movie shorts; not under episodes-of-*)
    wu_rows: list[dict] = []
    for p in pages:
        cp = p.get("categoryPath") or ""
        if not cp.startswith(WU_TEAS_CP_PREFIX):
            continue
        slug = p.get("slug") or ""
        if slug in WU_TEAS_EXCLUDE_SLUGS:
            continue
        if is_excluded_episode(p):
            continue
        wu_rows.append(p)
    if wu_rows:
        groups["wus-teas"] = wu_rows

    # Pilots: canonical four only, fixed order
    by_slug = {p.get("slug"): p for p in pages if (p.get("categoryPath") or "") == PILOT_CP}
    pilot_pages = [by_slug[s] for s in PILOT_SLUGS if s in by_slug]
    if pilot_pages:
        groups["pilot-episodes"] = pilot_pages

    html_cache: dict[str, str] = {}
    seasons_out: list[dict] = []

    for gid in sorted(groups.keys()):
        folder = group_key_to_folder(gid)
        season_href, title = resolve_season_hub(pages, folder_to_main, folder)
        if gid == "specials" and not season_href:
            title = "Specials"
        if gid == "pilot-episodes":
            title = "Pilot episodes"
            if not season_href:
                season_href = "/pages/content/year/2011/pilot-episodes/pilot-episodes"
        if gid == "wus-teas":
            title = "Wu's Teas"
            if not season_href:
                season_href = "/pages/content/mini-movies/wus-teas/wus-teas"

        season_title_for_search = title
        eps_raw = groups[gid]
        built_meta: list[dict] = []
        for p in eps_raw:
            built_meta.append(episode_row(p, thumbs, gid, season_title_for_search, html_cache))

        built_meta.sort(key=sort_key_for_ep)
        episodes: list[dict] = []
        for meta in built_meta:
            episodes.append(
                {
                    "display": meta["display"],
                    "href": meta["href"],
                    "slug": meta["slug"],
                    "filter": meta["filter"],
                    "codes": meta["codes"],
                    "img": meta["img"],
                }
            )

        seasons_out.append(
            {
                "id": gid,
                "title": title,
                "seasonHref": season_href,
                "episodes": episodes,
            }
        )

    seasons_out.sort(key=season_sort_key)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(
        json.dumps({"seasons": seasons_out}, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    n_eps = sum(len(s["episodes"]) for s in seasons_out)
    print(f"Wrote {OUT} — {len(seasons_out)} season groups, {n_eps} episodes")


if __name__ == "__main__":
    main()
