#!/usr/bin/env python3
"""
Resolve Fandom titles via MediaWiki redirects=1 + normalized titles, map to local hrefs
from wiki_pages.json (on-disk rows only), merge into site_routes.json.

Input: assets/data/uncovered_fandom_links.json (run report_uncovered_fandom_links.py first).

  python3 scripts/enrich_site_routes_with_redirects.py
  python3 scripts/enrich_site_routes_with_redirects.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
ROUTES = ROOT / "assets" / "data" / "site_routes.json"
UNCOVERED = ROOT / "assets" / "data" / "uncovered_fandom_links.json"
WIKI_PAGES = ROOT / "assets" / "data" / "wiki_pages.json"
API = "https://ninjago.fandom.com/api.php"
UA = "Mozilla/5.0 (compatible; NinjagoWikiLocalMirror/1.0)"

sys.path.insert(0, str(SCRIPT_DIR))
from rewrite_fandom_character_links import should_skip_wiki_path  # noqa: E402


def norm_title_key(s: str) -> str:
    return (
        urllib.parse.unquote(s or "")
        .replace("_", " ")
        .strip()
        .lower()
        .replace("  ", " ")
    )


def wiki_page_file_for_row(root: Path, row: dict) -> Path | None:
    slug = (row.get("slug") or "").strip()
    if not slug:
        return None
    href_row = (row.get("href") or "").strip()
    if href_row.startswith("/pages/"):
        rel = href_row[len("/pages/") :].strip("/")
        return root.joinpath("pages", *rel.split("/"), "index.html")
    return root / "pages" / slug / "index.html"


def load_title_to_href(root: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    with open(WIKI_PAGES, encoding="utf-8") as f:
        rows = json.load(f).get("pages") or []
    for row in rows:
        p = wiki_page_file_for_row(root, row)
        if p is None or not p.is_file():
            continue
        title = (row.get("wikiTitle") or row.get("display") or "").strip()
        if not title:
            continue
        href = (row.get("href") or "").strip()
        if not href.startswith("/"):
            slug = (row.get("slug") or "").strip()
            href = f"/pages/{slug}" if slug else ""
        if not href:
            continue
        out[norm_title_key(title)] = href
    return out


def apply_normalized_and_redirects(t: str, normalized: list, redirects: list) -> str:
    """t uses underscores like API 'from' fields. Chains normalize + redirect steps."""
    cur = t
    for _ in range(24):
        step = False
        for n in normalized or []:
            if n.get("from") == cur:
                cur = str(n.get("to", cur))
                step = True
                break
        if step:
            continue
        for r in redirects or []:
            if r.get("from") == cur:
                cur = str(r.get("to", cur))
                step = True
                break
        if not step:
            break
    return cur


def api_query_redirects_batch(titles: list[str]) -> tuple[list, list]:
    """Return (normalized, redirects) from MW API."""
    if not titles:
        return [], []
    titles_param = "|".join(urllib.parse.quote(t, safe="") for t in titles)
    url = f"{API}?action=query&format=json&redirects=1&titles={titles_param}"
    proc = subprocess.run(
        ["curl", "-sS", "-L", "-A", UA, "--max-time", "120", url],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or f"curl {proc.returncode}")
    data = json.loads(proc.stdout)
    q = data.get("query") or {}
    return q.get("normalized") or [], q.get("redirects") or []


def main() -> None:
    ap = argparse.ArgumentParser(description="Merge redirect-resolved wiki paths into site_routes.json")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--batch", type=int, default=35)
    ap.add_argument("--delay", type=float, default=0.12)
    args = ap.parse_args()
    root = args.root.resolve()

    if not UNCOVERED.is_file() or not ROUTES.is_file() or not WIKI_PAGES.is_file():
        print("Missing uncovered_fandom_links.json, site_routes.json, or wiki_pages.json", file=sys.stderr)
        sys.exit(1)

    title_to_href = load_title_to_href(root)

    with open(UNCOVERED, encoding="utf-8") as f:
        unc = json.load(f).get("uncovered") or []

    path_tails: list[str] = []
    for item in unc:
        wp = (item.get("wikiPath") or "").strip().lower()
        if not wp.startswith("/wiki/") or should_skip_wiki_path(wp):
            continue
        tail = wp[6:]
        if ":" in tail.split("/")[0]:
            continue
        path_tails.append(tail)

    path_tails = sorted(set(path_tails))
    # API titles: preserve underscores as in Fandom URLs
    titles = [t.replace(" ", "_") for t in path_tails]

    batches = [titles[i : i + args.batch] for i in range(0, len(titles), args.batch)]
    print(f"Resolving {len(titles)} title(s) in {len(batches)} API batch(es)…", file=sys.stderr)

    tail_to_canonical: dict[str, str] = {}
    for b in batches:
        try:
            normalized, redirects = api_query_redirects_batch(b)
        except (RuntimeError, json.JSONDecodeError, KeyError) as e:
            print(f"API batch failed: {e}", file=sys.stderr)
            continue
        for raw in b:
            final_unders = apply_normalized_and_redirects(raw, normalized, redirects)
            final_spaced = final_unders.replace("_", " ").strip()
            tail_to_canonical[raw.lower()] = final_spaced
        if args.delay > 0:
            time.sleep(args.delay)

    path_to_local: dict[str, str] = {}
    with open(ROUTES, encoding="utf-8") as f:
        routes = json.load(f)
    existing = {k.lower(): v for k, v in (routes.get("wikiPathToHref") or {}).items()}

    for tail in path_tails:
        unders = tail.replace(" ", "_")
        canonical = tail_to_canonical.get(unders.lower()) or tail_to_canonical.get(tail.lower())
        if not canonical:
            continue
        href = title_to_href.get(norm_title_key(canonical))
        if not href:
            continue
        pl = ("/wiki/" + unders).lower()
        if pl in existing:
            continue
        path_to_local[pl] = href
        if "_" in pl:
            path_to_local[pl.replace("_", " ")] = href

    print(f"New redirect/normalize path mappings: {len(path_to_local)}", file=sys.stderr)

    if args.dry_run:
        for k, v in sorted(path_to_local.items())[:40]:
            print(f"  {k!r} -> {v}")
        return

    merged_paths = dict(routes.get("wikiPathToHref") or {})
    for k, v in path_to_local.items():
        merged_paths.setdefault(k, v)
    routes["wikiPathToHref"] = dict(sorted(merged_paths.items()))

    from build_site_routes import wiki_title_from_path  # noqa: E402

    wiki_title_key_to_href: dict[str, str] = dict(routes.get("wikiTitleKeyToHref") or {})
    for path, href in path_to_local.items():
        if not path.startswith("/wiki/"):
            continue
        title = wiki_title_from_path(path)
        if not title:
            continue
        wiki_title_key_to_href.setdefault(title.lower(), href)

    routes["wikiTitleKeyToHref"] = dict(sorted(wiki_title_key_to_href.items()))
    routes.setdefault("stats", {})
    routes["stats"]["redirectAliasesAdded"] = len(path_to_local)

    with open(ROUTES, "w", encoding="utf-8") as f:
        json.dump(routes, f, ensure_ascii=False, indent=2)
        f.write("\n")
    print(f"Wrote {ROUTES}. Re-run: python3 scripts/rewrite_fandom_character_links.py --apply", file=sys.stderr)


if __name__ == "__main__":
    main()
