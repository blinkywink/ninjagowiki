#!/usr/bin/env python3
"""
Build a JSON tree of the Ninjago Fandom wiki category hierarchy starting at
Category:Content (https://ninjago.fandom.com/wiki/Category:Content).

Uses the MediaWiki API (categorymembers). Respects continuations.

Default export lists **subcategories only**. To also fetch **article titles** listed on each category
(so the All pages UI and scripts can match wiki pages to local mirrors), add:

  --include-direct-pages

That roughly **doubles** API traffic and JSON size; use --no-sleep carefully.

Run from repo root:

  python3 scripts/fetch_fandom_content_category_tree.py
  python3 -u scripts/fetch_fandom_content_category_tree.py --no-sleep --max-depth 8
  python3 -u scripts/fetch_fandom_content_category_tree.py --no-sleep --include-direct-pages --progress-every 50

After importing new local pages, refresh routing for the tree UI:

  python3 scripts/build_site_routes.py

Output: assets/data/fandom_content_category_tree.json
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
OUT_PATH = ROOT / "assets" / "data" / "fandom_content_category_tree.json"

API = "https://ninjago.fandom.com/api.php"
UA = "NinjagoSiteMirror/1.0 (local mirror; contact: site maintainer)"

# Line-buffer / flush so progress shows immediately in the terminal (especially with pipes).
try:
    sys.stderr.reconfigure(line_buffering=True)
except (AttributeError, OSError):
    pass


def log(msg: str) -> None:
    print(msg, file=sys.stderr, flush=True)


def slugify_category_title(title: str) -> str:
    """Category:Foo_bar -> foo-bar for URL segments."""
    t = title.strip()
    if t.startswith("Category:"):
        t = t[len("Category:") :]
    t = t.lower()
    t = re.sub(r"[^\w\s-]", "", t, flags=re.UNICODE)
    t = re.sub(r"[-\s]+", "-", t).strip("-")
    return t or "category"


def api_get(params: dict[str, str]) -> dict:
    """HTTPS via curl (matches import_wiki_character.py; avoids macOS Python SSL issues)."""
    q = urllib.parse.urlencode(params)
    url = f"{API}?{q}"
    proc = subprocess.run(
        ["curl", "-sS", "-L", "-A", UA, "--max-time", "120", url],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or f"curl exit {proc.returncode}")
    return json.loads(proc.stdout)


def fetch_subcategories(
    cmtitle: str,
    sleep_s: float,
    *,
    depth: int,
    cache: dict[str, list[str]],
) -> list[str]:
    """Return sorted list of full category titles (Category:...) that are direct subcats."""
    if cmtitle in cache:
        log(f"[depth {depth}] CACHE hit subcategories: {cmtitle}")
        return list(cache[cmtitle])

    titles: list[str] = []
    cmcontinue: str | None = None
    page_idx = 0
    while True:
        if sleep_s > 0:
            time.sleep(sleep_s)
        if page_idx == 0:
            log(f"[depth {depth}] Fetching subcategories for: {cmtitle}")
        else:
            log(f"[depth {depth}] continuation (cmcontinue) subcategories: {cmtitle}")
        page_idx += 1

        params: dict[str, str] = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": cmtitle,
            "cmtype": "subcat",
            "cmlimit": "500",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = api_get(params)
        members = (data.get("query") or {}).get("categorymembers") or []
        for m in members:
            t = (m.get("title") or "").strip()
            if t:
                titles.append(t)
        cont = data.get("continue") or {}
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue:
            break

    result = sorted(set(titles))
    cache[cmtitle] = result
    return result


def fetch_direct_pages(
    cmtitle: str,
    sleep_s: float,
    *,
    depth: int,
    cache: dict[str, list[str]],
) -> list[str]:
    """Non-category members listed directly on the category page (rare under Content)."""
    if cmtitle in cache:
        log(f"[depth {depth}] CACHE hit direct pages: {cmtitle}")
        return list(cache[cmtitle])

    titles: list[str] = []
    cmcontinue: str | None = None
    page_idx = 0
    while True:
        if sleep_s > 0:
            time.sleep(sleep_s)
        if page_idx == 0:
            log(f"[depth {depth}] Fetching direct pages for: {cmtitle}")
        else:
            log(f"[depth {depth}] continuation (cmcontinue) direct pages: {cmtitle}")
        page_idx += 1

        params: dict[str, str] = {
            "action": "query",
            "format": "json",
            "list": "categorymembers",
            "cmtitle": cmtitle,
            "cmtype": "page",
            "cmlimit": "500",
        }
        if cmcontinue:
            params["cmcontinue"] = cmcontinue
        data = api_get(params)
        members = (data.get("query") or {}).get("categorymembers") or []
        for m in members:
            t = (m.get("title") or "").strip()
            if t:
                titles.append(t)
        cont = data.get("continue") or {}
        cmcontinue = cont.get("cmcontinue")
        if not cmcontinue:
            break

    result = sorted(set(titles))
    cache[cmtitle] = result
    return result


def build_tree_node(
    title: str,
    *,
    depth: int,
    max_depth: int,
    sleep_s: float,
    visited: set[str],
    include_direct_pages: bool,
    subcat_cache: dict[str, list[str]],
    page_cache: dict[str, list[str]],
    visit_counter: list[int],
    progress_every: int,
) -> dict:
    display = title[9:] if title.startswith("Category:") else title
    slug = slugify_category_title(title)
    wiki_path = title.replace(" ", "_")
    wiki_url = "https://ninjago.fandom.com/wiki/" + urllib.parse.quote(wiki_path, safe="():'%!")

    node: dict = {
        "title": title,
        "displayName": display,
        "slug": slug,
        "wikiUrl": wiki_url,
        "depth": depth,
        "children": [],
        "directPages": [],
    }

    if depth >= max_depth:
        node["truncated"] = True
        return node

    if title in visited:
        node["duplicate"] = True
        return node
    visited.add(title)
    visit_counter[0] += 1
    n = visit_counter[0]
    log(f"Visited {n} categories so far… (current: {title})")
    if progress_every > 0 and n % progress_every == 0:
        log(f"── Progress: {n} categories visited (still walking the tree…) ──")

    try:
        subs = fetch_subcategories(title, sleep_s, depth=depth, cache=subcat_cache)
        pages = (
            fetch_direct_pages(title, sleep_s, depth=depth, cache=page_cache)
            if include_direct_pages
            else []
        )
    except Exception as e:
        node["error"] = str(e)
        return node

    node["directPages"] = pages
    for sub in subs:
        log(f"[depth {depth}] Recursing into child: {sub}")
        node["children"].append(
            build_tree_node(
                sub,
                depth=depth + 1,
                max_depth=max_depth,
                sleep_s=sleep_s,
                visited=visited,
                include_direct_pages=include_direct_pages,
                subcat_cache=subcat_cache,
                page_cache=page_cache,
                visit_counter=visit_counter,
                progress_every=progress_every,
            )
        )

    return node


def count_nodes(n: dict) -> tuple[int, int]:
    """Return (total_nodes, leaf_count)."""
    ch = n.get("children") or []
    if not ch:
        return 1, 1
    t, leaves = 1, 0
    for c in ch:
        ct, cl = count_nodes(c)
        t += ct
        leaves += cl
    return t, leaves


def main() -> None:
    ap = argparse.ArgumentParser(description="Fetch Category:Content subtree from Ninjago Fandom API.")
    ap.add_argument("--root", default="Category:Content", help="Root category title (default: Category:Content)")
    ap.add_argument("--max-depth", type=int, default=8, help="Max nesting depth (default: 8)")
    ap.add_argument("--sleep", type=float, default=0.1, help="Seconds between API calls (default: 0.1)")
    ap.add_argument(
        "--no-sleep",
        action="store_true",
        help="Do not sleep between API calls (faster; be kind to Fandom if batching large trees).",
    )
    ap.add_argument(
        "--include-direct-pages",
        action="store_true",
        help="Also list non-category members per category (doubles API traffic).",
    )
    ap.add_argument("-o", "--output", type=Path, default=OUT_PATH, help="Output JSON path")
    ap.add_argument(
        "--progress-every",
        type=int,
        default=25,
        metavar="N",
        help="Print an extra milestone line every N categories (0 = off). Default: 25.",
    )
    args = ap.parse_args()

    sleep_s = 0.0 if args.no_sleep else args.sleep
    visited: set[str] = set()
    subcat_cache: dict[str, list[str]] = {}
    page_cache: dict[str, list[str]] = {}
    visit_counter = [0]

    log(
        f"Building tree from {args.root!r} (max_depth={args.max_depth}, sleep={sleep_s})…",
    )

    tree = build_tree_node(
        args.root,
        depth=0,
        max_depth=args.max_depth,
        sleep_s=sleep_s,
        visited=visited,
        include_direct_pages=args.include_direct_pages,
        subcat_cache=subcat_cache,
        page_cache=page_cache,
        visit_counter=visit_counter,
        progress_every=args.progress_every,
    )

    total, leaves = count_nodes(tree)
    payload = {
        "v": 1,
        "generatedAt": datetime.now(timezone.utc).isoformat(),
        "api": API,
        "rootTitle": args.root,
        "maxDepth": args.max_depth,
        "stats": {
            "uniqueCategoriesVisited": len(visited),
            "treeNodes": total,
            "treeLeaves": leaves,
        },
        "tree": tree,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    log(
        f"Wrote {args.output} ({len(visited)} categories visited, {total} nodes in tree display).",
    )


if __name__ == "__main__":
    main()
