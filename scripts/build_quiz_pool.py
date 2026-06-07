#!/usr/bin/env python3
"""Build assets/data/quiz_pool.json — images for trivia quizzes."""

from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "assets" / "data"
OUT = DATA / "quiz_pool.json"

_WIKIA = "static.wikia.nocookie.net"
_JUNK = re.compile(r"noimage|spacer|logo\.png|brand-img|svg", re.I)
_TITLE_CARD = re.compile(r"titlecard|title.card|title_card|title-card", re.I)
_VIDEO_URL = re.compile(
    r"Full_Episode|Full_Episodes|Cartoon_Network|Character_Spot|"
    r"LEGO_Ninjago_-_Season|Episode_\d+_LEGO|"
    r"Soundtrack|compilation|Animation_for_Kids|"
    r"Jay_Vincent|Ninjago_Soundtrack|\(Clip\)|"
    r"ytimg|youtube|video-thumbnail",
    re.I,
)
CHARACTER_MIN_IMAGES = 6
WEAPON_MIN_IMAGES = 15
# Main-line boxed Ninjago sets (705xx–707xx, 717xx–718xx, etc.) — not polybags, magazines, merch.
_TRADITIONAL_SET = re.compile(r"^(70[5-9]\d{2}|71[0-9]\d{2})$")


def _set_code(row: dict) -> str:
    codes = row.get("codes") or []
    if codes:
        return str(codes[0])
    m = re.match(r"^(\d+)", row.get("display") or "")
    return m.group(1) if m else ""


def _is_traditional_retail_set(row: dict) -> bool:
    return bool(_TRADITIONAL_SET.match(_set_code(row)))


def _norm(url: str) -> str:
    u = (url or "").strip()
    u = re.sub(r"/scale-to-width-down/\d+", "", u, flags=re.I)
    u = re.sub(r"/scale-to-width/\d+", "", u, flags=re.I)
    return u.lower()


def _upgrade_image_url(url: str, width: int = 800) -> str:
    u = (url or "").strip()
    if not u:
        return u
    u = re.sub(r"/scale-to-width-down/\d+", f"/scale-to-width-down/{width}", u, flags=re.I)
    u = re.sub(r"/scale-to-width/\d+", f"/scale-to-width/{width}", u, flags=re.I)
    return u


def extract_release_year(html: str, *, href: str, group_title: str) -> int | None:
    m = re.search(
        r'data-source="released"[\s\S]*?pi-data-value[^>]*>([\s\S]*?)</div>',
        html,
        re.I,
    )
    if m:
        years = re.findall(r"\b(20\d{2})\b", m.group(1))
        if years:
            return int(years[-1])

    m = re.search(r"\b(20\d{2})\b", group_title or "")
    if m:
        return int(m.group(1))

    m = re.search(r"/year/(20\d{2})/", href)
    if m:
        return int(m.group(1))

    return None


def _good_url(url: str) -> bool:
    u = (url or "").strip()
    if not u or u.startswith("data:"):
        return False
    if _WIKIA not in u and not u.startswith("/assets/"):
        return False
    if _JUNK.search(u):
        return False
    return True


def _img_srcs_from_attrs(blob: str) -> list[str]:
    out: list[str] = []
    for m in re.finditer(r'\b(?:src|data-src)=["\']([^"\']+)["\']', blob, re.I):
        out.append(m.group(1).strip())
    return out


def _strip_non_screenshot_html(html: str) -> str:
    chunk = html
    chunk = re.sub(r"<aside[\s\S]*?</aside>", " ", chunk, flags=re.I)
    chunk = re.sub(r"<noscript>[\s\S]*?</noscript>", " ", chunk, flags=re.I)
    chunk = re.sub(
        r'<details class="wiki-char-msection">\s*'
        r'<summary class="wiki-char-msection-sum">Videos</summary>[\s\S]*?</details>',
        " ",
        chunk,
        flags=re.I,
    )
    chunk = re.sub(
        r'<figure class="pi-item pi-image"[\s\S]*?</figure>',
        " ",
        chunk,
        flags=re.I,
    )
    chunk = re.sub(
        r'<a\b[^>]*(?:data-youtube-id|video-thumbnail)[^>]*>[\s\S]*?</a>',
        " ",
        chunk,
        flags=re.I,
    )
    return chunk


def _img_is_screenshot(*, img_tag: str, src: str, html: str, pos: int) -> bool:
    if re.search(r"data-video-name|data-video-key|pi-image-thumbnail", img_tag, re.I):
        return False
    if _TITLE_CARD.search(src):
        return False
    if _VIDEO_URL.search(src):
        return False

    window = html[max(0, pos - 1200) : pos]
    if re.search(
        r"<a\b[^>]*(?:data-youtube-id|video-thumbnail)[^>]*>(?:(?!</a>).)*$",
        window,
        re.I | re.DOTALL,
    ):
        return False
    return True


def extract_quiz_images(html: str, *, exclude: set[str] | None = None) -> list[str]:
    exclude = exclude or set()
    main = re.search(r"<main\b[^>]*>([\s\S]*)</main>", html, re.I)
    chunk = main.group(1) if main else html
    chunk = _strip_non_screenshot_html(chunk)

    seen: set[str] = set()
    urls: list[str] = []

    for m in re.finditer(r"<img\b([^>]+)>", chunk, re.I):
        img_tag = m.group(0)
        for src in _img_srcs_from_attrs(m.group(1)):
            if not _good_url(src):
                continue
            if not _img_is_screenshot(img_tag=img_tag, src=src, html=chunk, pos=m.start()):
                continue
            key = _norm(src)
            if key in seen or key in exclude:
                continue
            seen.add(key)
            urls.append(_upgrade_image_url(src))

    return urls


def _read_html(href: str) -> str | None:
    path = ROOT / href.strip("/") / "index.html"
    if not path.is_file():
        path = ROOT / href.strip("/")
    if not path.is_file():
        return None
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def build_episodes() -> list[dict]:
    data = json.loads((DATA / "episodes_index.json").read_text(encoding="utf-8"))
    out: list[dict] = []
    for season in data.get("seasons") or []:
        for ep in season.get("episodes") or []:
            href = ep.get("href") or ""
            display = ep.get("display") or ""
            if not href or not display:
                continue
            html = _read_html(href)
            if not html:
                continue
            exclude = {_norm(ep.get("img") or "")}
            imgs = extract_quiz_images(html, exclude=exclude)
            if len(imgs) < 1:
                continue
            out.append(
                {
                    "display": display,
                    "href": href,
                    "images": imgs[:24],
                }
            )
    return out


def build_characters() -> list[dict]:
    data = json.loads((DATA / "characters.json").read_text(encoding="utf-8"))
    out: list[dict] = []
    for row in data.get("characters") or []:
        href = row.get("href") or ""
        display = row.get("display") or ""
        slug = row.get("slug") or ""
        if not href or not display:
            continue
        html = _read_html(href)
        if not html:
            continue
        exclude = {_norm(row.get("img") or "")}
        imgs = extract_quiz_images(html, exclude=exclude)
        if len(imgs) < CHARACTER_MIN_IMAGES:
            continue
        out.append(
            {
                "display": display,
                "href": href,
                "slug": slug,
                "images": imgs[:24],
            }
        )
    return out


def build_sets() -> list[dict]:
    data = json.loads((DATA / "sets_index.json").read_text(encoding="utf-8"))
    out: list[dict] = []
    for group in data.get("groups") or []:
        group_title = group.get("title") or ""
        for row in group.get("sets") or []:
            href = row.get("href") or ""
            display = row.get("display") or ""
            if not href or not display:
                continue
            if not _is_traditional_retail_set(row):
                continue
            html = _read_html(href)
            if not html:
                continue
            year = extract_release_year(html, href=href, group_title=group_title)
            if year is None:
                continue
            exclude = {_norm(row.get("img") or "")}
            imgs = extract_quiz_images(html, exclude=exclude)
            if len(imgs) < 1:
                continue
            out.append(
                {
                    "display": display,
                    "href": href,
                    "year": year,
                    "setNumber": _set_code(row),
                    "images": imgs[:24],
                }
            )
    return out


def build_weapons() -> list[dict]:
    data = json.loads((DATA / "weapons_index.json").read_text(encoding="utf-8"))
    seen_hrefs: set[str] = set()
    out: list[dict] = []
    for group in data.get("groups") or []:
        for row in group.get("sets") or []:
            href = row.get("href") or ""
            display = row.get("display") or ""
            if not href or not display or href in seen_hrefs:
                continue
            seen_hrefs.add(href)
            html = _read_html(href)
            if not html:
                continue
            exclude = {_norm(row.get("img") or "")}
            imgs = extract_quiz_images(html, exclude=exclude)
            if len(imgs) < WEAPON_MIN_IMAGES:
                continue
            out.append(
                {
                    "display": display,
                    "href": href,
                    "images": imgs[:24],
                }
            )
    return out


def main() -> None:
    payload = {
        "v": 1,
        "episodes": build_episodes(),
        "characters": build_characters(),
        "sets": build_sets(),
        "weapons": build_weapons(),
    }
    OUT.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"Wrote {OUT.name}: "
        f"{len(payload['episodes'])} episodes, "
        f"{len(payload['characters'])} characters, "
        f"{len(payload['sets'])} sets, "
        f"{len(payload['weapons'])} weapons"
    )


if __name__ == "__main__":
    main()
