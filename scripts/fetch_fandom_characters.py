#!/usr/bin/env python3
"""
Fetch every *article* in https://ninjago.fandom.com/wiki/Category:Characters (API cmtype=page).

Fandom shows “1398” total = 1244 character articles + 154 subcategory pages (cmtype=subcat).
We only pull articles (not Category:* subcategory members). Template:/Module:/… junk titles are skipped.

Writes:
  scripts/cat_all_characters_with_thumbs.json
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from pathlib import Path
from urllib.parse import quote, urlencode

UA = "Mozilla/5.0 (compatible; NinjagoWikiMirror/1.0; +local-educational-use)"
API = "https://ninjago.fandom.com/api.php"

SKIP_PREFIXES = ("Category:", "Template:", "Module:", "MediaWiki:", "Help:", "File:", "User:")
EXCLUDE_TITLES = frozenset({"2Morrow"})
OUT_FILE = "cat_all_characters_with_thumbs.json"


def curl_json(params: dict) -> dict:
    qs = urlencode(params, safe="", quote_via=quote)
    url = f"{API}?{qs}"
    out = subprocess.check_output(
        ["curl", "-fsSL", "-A", UA, url],
        text=True,
    )
    return json.loads(out)


def slugify(title: str) -> str:
    s = title.lower()
    s = re.sub(r"[^\w\s-]", "", s, flags=re.ASCII)
    s = re.sub(r"[-\s]+", "-", s).strip("-")
    return s or "x"


def fetch_all_category_pages() -> list[dict]:
    members: list[dict] = []
    cmcontinue: str | None = None
    while True:
        params: dict = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": "Category:Characters",
            "cmlimit": "500",
            "cmtype": "page",
            "cmprop": "title",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = curl_json(params)
        members.extend(data["query"]["categorymembers"])
        cmcontinue = data.get("continue", {}).get("cmcontinue")
        if not cmcontinue:
            break
        time.sleep(0.15)
    return members


def filter_main_articles(members: list[dict]) -> list[dict]:
    return [m for m in members if not m["title"].startswith(SKIP_PREFIXES)]


def fetch_thumbnails(titles: list[str]) -> list[dict]:
    """One row per title, same order as `titles` (thumbnail may be null)."""
    out_rows: list[dict] = []
    batch_size = 45
    for i in range(0, len(titles), batch_size):
        batch = titles[i : i + batch_size]
        params = {
            "action": "query",
            "format": "json",
            "titles": "|".join(batch),
            "prop": "pageimages",
            "piprop": "thumbnail",
            "pithumbsize": "220",
        }
        data = curl_json(params)
        raw_pages = data.get("query", {}).get("pages", {}).values()
        by_title = {p.get("title", ""): p for p in raw_pages}
        for t in batch:
            page = by_title.get(t, {})
            thumb = (page.get("thumbnail") or {}).get("source")
            base_slug = slugify(t)
            out_rows.append({"title": t, "slug": base_slug, "thumb_url": thumb})
        time.sleep(0.15)
    return out_rows


def uniquify_slugs(rows: list[dict]) -> list[dict]:
    seen: dict[str, int] = {}
    out: list[dict] = []
    for row in rows:
        base = row["slug"]
        n = seen.get(base, 0)
        if n:
            row = {**row, "slug": f"{base}-{n + 1}"}
        seen[base] = n + 1
        out.append(row)
    return out


def main() -> int:
    scripts_dir = Path(__file__).resolve().parent
    members = filter_main_articles(fetch_all_category_pages())
    titles = [m["title"] for m in members if m["title"] not in EXCLUDE_TITLES]

    print(
        f"Category:Characters articles (cmtype=page, after filters): {len(titles)}",
    )
    print("(Fandom “1398” = these articles + 154 subcategory subpages.)")

    rows = uniquify_slugs(fetch_thumbnails(titles))
    out_path = scripts_dir / OUT_FILE
    out_path.write_text(json.dumps(rows, indent=2), encoding="utf-8")
    print(f"Wrote {len(rows)} entries to {OUT_FILE}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
