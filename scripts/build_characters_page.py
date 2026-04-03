#!/usr/bin/env python3
"""
Download Fandom category thumbnails, write assets/data/characters.json, refresh homepage search index.

Prerequisite: scripts/fetch_fandom_characters.py (writes cat_all_characters_with_thumbs.json)
"""
from __future__ import annotations

import html
import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote

UA = "Mozilla/5.0 (compatible; NinjagoWikiMirror/1.0; local-educational)"

ROOT = Path(__file__).resolve().parents[1]
ASSET_DIR = ROOT / "assets" / "characters"
JSON_PATH = ROOT / "scripts" / "cat_all_characters_with_thumbs.json"
INDEX_HTML = ROOT / "index.html"
DATA_DIR = ROOT / "assets" / "data"
CHARACTERS_JSON = DATA_DIR / "characters.json"

FEATURED: list[dict] = [
    {"wiki_title": "Lloyd", "display": "Lloyd", "slug": "lloyd", "local": "lloyd.webp", "filter": "lloyd green ninja"},
    {"wiki_title": "Kai", "display": "Kai", "filter": "kai fire ninja"},
    {"wiki_title": "Jay", "display": "Jay", "filter": "jay lightning ninja"},
    {"wiki_title": "Cole", "display": "Cole", "filter": "cole earth ninja"},
    {"wiki_title": "Zane", "display": "Zane", "filter": "zane ice ninja nindroid"},
    {"wiki_title": "Nya", "display": "Nya", "filter": "nya water ninja"},
    {"wiki_title": "Wu", "display": "Sensei Wu", "filter": "wu sensei master sensei wu"},
    {"wiki_title": "Garmadon", "display": "Garmadon", "filter": "garmadon lord garmadon"},
    {"wiki_title": "Pythor", "display": "Pythor", "filter": "pythor serpentine"},
    {"wiki_title": "The Overlord", "display": "Overlord", "slug": "overlord", "filter": "overlord darkness"},
]


def curl_json(url: str) -> dict:
    raw = subprocess.check_output(["curl", "-fsSL", "-A", UA, url], text=True)
    return json.loads(raw)


def wiki_url(title: str) -> str:
    return "https://ninjago.fandom.com/wiki/" + quote(title.replace(" ", "_"), safe="")


def abs_asset(path: str) -> str:
    """Root-absolute path for <img> and search thumbs (works from /characters/…)."""
    if path.startswith("./"):
        return "/" + path[2:]
    if path.startswith("/"):
        return path
    return path


def character_href(slug: str, wiki_title: str) -> str:
    if slug == "kai":
        return "/characters/kai"
    return wiki_url(wiki_title)


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.ASCII)
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return s or "x"


def search_keywords_from_title(title: str) -> str:
    return re.sub(r"[^a-z0-9]+", " ", title.lower()).strip()


def sniff_ext(data: bytes) -> str:
    if data.startswith(b"\xff\xd8\xff"):
        return ".jpg"
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return ".png"
    if len(data) >= 12 and data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    if data.startswith((b"GIF87a", b"GIF89a")):
        return ".gif"
    return ".img"


def download(url: str, dest_base: Path) -> Path:
    tmp = dest_base.with_suffix(".dl")
    last_err: Exception | None = None
    for attempt in range(5):
        if tmp.exists():
            tmp.unlink()
        try:
            subprocess.run(
                ["curl", "-fsSL", "-A", UA, "-o", str(tmp), url],
                check=True,
            )
            ext = sniff_ext(tmp.read_bytes()[:16])
            final = dest_base.with_suffix(ext)
            if final.exists() and final != tmp:
                final.unlink()
            tmp.rename(final)
            return final
        except subprocess.CalledProcessError as e:
            last_err = e
            time.sleep(1.2 * (attempt + 1))
    raise last_err  # type: ignore[misc]


def existing_asset(slug: str) -> str | None:
    matches = [p for p in ASSET_DIR.glob(slug + ".*") if p.suffix != ".dl"]
    if not matches:
        return None
    return "./assets/characters/" + matches[0].name


def ensure_image(slug: str, url: str | None) -> str:
    if not url:
        return "./assets/hero.png"
    hit = existing_asset(slug)
    if hit:
        return hit
    print("download", slug)
    try:
        final = download(url, ASSET_DIR / slug)
        time.sleep(0.06)
        return "./assets/characters/" + final.name
    except subprocess.CalledProcessError:
        print("  (failed CDN, hero fallback)", slug)
        return "./assets/hero.png"


def fill_featured_thumbs() -> None:
    titles = "|".join(f["wiki_title"] for f in FEATURED if not f.get("local"))
    api = (
        "https://ninjago.fandom.com/api.php?action=query&format=json&"
        f"titles={quote(titles, safe='')}&prop=pageimages&piprop=thumbnail&pithumbsize=220"
    )
    data = curl_json(api)
    by_title = {p["title"]: p for p in data.get("query", {}).get("pages", {}).values()}
    for f in FEATURED:
        if f.get("local"):
            continue
        wt = f["wiki_title"]
        page = by_title.get(wt)
        f["thumb_url"] = (page.get("thumbnail") or {}).get("source") if page else None
        if not f.get("slug"):
            f["slug"] = slugify(wt)


def search_link(*, slug: str, display: str, data_filter: str, thumb: str) -> str:
    esc = html.escape
    t = abs_asset(thumb)
    if slug == "kai":
        page_href = "/characters/kai"
    else:
        page_href = f"/characters#{esc(slug)}"
    return (
        f'        <a href="{page_href}" data-search="{esc(data_filter)}" data-search-thumb="{esc(t)}">'
        f'<span class="article-name">{esc(display)}</span></a>'
    )


def replace_hidden_search(html_in: str, inner: str) -> str:
    start_marker = '<div aria-hidden="true" style="display:none">'
    i = html_in.index(start_marker) + len(start_marker)
    end = html_in.index("\n      </div>\n    </main>", i)
    return html_in[:i] + "\n" + inner + html_in[end:]


def main() -> int:
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    fill_featured_thumbs()
    if not JSON_PATH.exists():
        raise SystemExit(
            f"Missing {JSON_PATH.name} — run: python3 scripts/fetch_fandom_characters.py"
        )
    rows: list[dict] = json.loads(JSON_PATH.read_text(encoding="utf-8"))
    featured_slugs = {f["slug"] for f in FEATURED}
    seen: set[str] = set()
    deduped: list[dict] = []
    for row in rows:
        s = row["slug"]
        if s in featured_slugs or s in seen:
            continue
        seen.add(s)
        deduped.append(row)
    rows = deduped

    manifest: list[dict] = []
    search_entries: list[str] = []

    for f in FEATURED:
        slug = f["slug"]
        if f.get("local"):
            img_rel = abs_asset("./assets/" + f["local"])
        else:
            img_rel = abs_asset(ensure_image(slug, f.get("thumb_url")))
        manifest.append(
            {
                "slug": slug,
                "href": character_href(slug, f["wiki_title"]),
                "wikiUrl": wiki_url(f["wiki_title"]),
                "display": f["display"],
                "filter": f["filter"],
                "img": img_rel,
            }
        )
        search_entries.append(
            search_link(slug=slug, display=f["display"], data_filter=f["filter"], thumb=img_rel)
        )

    for row in rows:
        slug = row["slug"]
        title = row["title"]
        img_rel = abs_asset(ensure_image(slug, row.get("thumb_url")))
        filt = search_keywords_from_title(title)
        manifest.append(
            {
                "slug": slug,
                "href": character_href(slug, title),
                "wikiUrl": wiki_url(title),
                "display": title,
                "filter": filt,
                "img": img_rel,
            }
        )
        search_entries.append(
            search_link(slug=slug, display=title, data_filter=filt, thumb=img_rel)
        )

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CHARACTERS_JSON.write_text(
        json.dumps({"v": 1, "characters": manifest}, ensure_ascii=False),
        encoding="utf-8",
    )

    search_joined = "\n".join(search_entries)

    idx = INDEX_HTML.read_text(encoding="utf-8")
    idx = replace_hidden_search(idx, search_joined)
    INDEX_HTML.write_text(idx, encoding="utf-8")

    print(
        "Updated",
        INDEX_HTML.name,
        ",",
        CHARACTERS_JSON.relative_to(ROOT),
        f"({len(manifest)} characters)",
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
