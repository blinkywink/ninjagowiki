#!/usr/bin/env python3
"""
Scan local HTML for ninjago.fandom.com/wiki/ links to *article* pages we do not mirror yet.

Skips Category:, File:, Template:, etc. (same rules as rewrite_fandom_character_links.py).
Compares against assets/data/site_routes.json (run build_site_routes.py first).

Outputs:
  - assets/data/uncovered_fandom_links.json (aggregated by wiki path)
  - Summary on stderr

Next steps (manual / future scripts):
  - For character articles: import via scripts/import_wiki_character.py + characters.json workflow.
  - For other namespaces: design pages/<slug>/ or a generic wiki article importer, then extend
    build_site_routes.py to list those paths.

  Re-fetch the category tree with direct pages included so the All pages tree lists articles:
    python3 -u scripts/fetch_fandom_content_category_tree.py --no-sleep --include-direct-pages

  python3 scripts/report_uncovered_fandom_links.py
  python3 scripts/report_uncovered_fandom_links.py --limit-files 50
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from pathlib import Path
from urllib.parse import unquote

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
ROUTES_JSON = ROOT / "assets" / "data" / "site_routes.json"
OUT_JSON = ROOT / "assets" / "data" / "uncovered_fandom_links.json"

sys.path.insert(0, str(SCRIPT_DIR))
from rewrite_fandom_character_links import (  # noqa: E402
    A_HREF_RE,
    iter_html_files,
    local_href_for_url,
    parse_href_for_lookup,
    should_skip_wiki_path,
)


def load_wiki_path_to_href(path: Path) -> dict[str, str]:
    if not path.is_file():
        return {}
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    raw = data.get("wikiPathToHref") or {}
    return {str(k).lower(): str(v) for k, v in raw.items()}


def main() -> None:
    ap = argparse.ArgumentParser(description="Report Fandom wiki links not mirrored locally.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--routes", type=Path, default=ROUTES_JSON)
    ap.add_argument("-o", "--output", type=Path, default=OUT_JSON)
    ap.add_argument("--limit-files", type=int, default=0, metavar="N", help="Scan at most N html files (0=all).")
    ap.add_argument("--ignore-dir", action="append", default=[], metavar="NAME")
    args = ap.parse_args()
    root: Path = args.root.resolve()

    path_to_local = load_wiki_path_to_href(args.routes)
    if not path_to_local:
        print(f"Missing or empty {args.routes} — run python3 scripts/build_site_routes.py", file=sys.stderr)
        sys.exit(1)

    html_files = iter_html_files(root, args.ignore_dir)
    if args.limit_files > 0:
        html_files = html_files[: args.limit_files]

    # path_low -> { "count": n, "sample_href": str, "sources": [rel paths] }
    agg: dict[str, dict] = {}

    for fp in html_files:
        text = fp.read_text(encoding="utf-8")
        rel = str(fp.relative_to(root))
        for m in A_HREF_RE.finditer(text):
            url = m.group("url")
            pl, _frag, _q = parse_href_for_lookup(url)
            if pl is None:
                continue
            if should_skip_wiki_path(pl):
                continue
            if local_href_for_url(url, path_to_local):
                continue
            entry = agg.setdefault(
                pl,
                {"wikiPath": pl, "count": 0, "sampleHref": url.strip(), "sources": []},
            )
            entry["count"] += 1
            if len(entry["sources"]) < 8 and rel not in entry["sources"]:
                entry["sources"].append(rel)

    items = sorted(agg.values(), key=lambda x: (-x["count"], x["wikiPath"]))
    payload = {
        "v": 1,
        "stats": {
            "distinctUncoveredWikiPaths": len(items),
            "htmlFilesScanned": len(html_files),
        },
        "uncovered": items,
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
        f.write("\n")

    title_hint = [
        unquote(p["wikiPath"].split("/wiki/", 1)[-1]).replace("_", " ")
        for p in items[:15]
    ]
    print(
        f"Wrote {args.output} — {len(items)} distinct uncovered article paths "
        f"({sum(x['count'] for x in items)} total link hits), scanned {len(html_files)} HTML files.",
        file=sys.stderr,
    )
    if title_hint:
        print("Examples (wiki titles): " + "; ".join(title_hint), file=sys.stderr)


if __name__ == "__main__":
    main()
