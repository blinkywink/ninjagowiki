#!/usr/bin/env python3
"""
Resolve local `_unsorted` wiki pages into category-tree paths using live Fandom page categories.

For each row in assets/data/wiki_pages.json with categoryPath == "_unsorted":
  1) Query MediaWiki API for that page's categories.
  2) Map category titles to known slug paths from fandom_content_category_tree.json.
  3) Pick the deepest matching path (stable lexical tiebreaker).
  4) Move pages/_unsorted/<slug>/ -> pages/<categoryPath>/<slug>/ and update manifest row.

Then run:
  python3 scripts/build_site_routes.py
"""

from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
import time
import urllib.parse
from pathlib import Path

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
WIKI_PAGES_JSON = ROOT / "assets" / "data" / "wiki_pages.json"

sys.path.insert(0, str(SCRIPT_DIR))
from wiki_tree_category_paths import load_tree  # noqa: E402

API = "https://ninjago.fandom.com/api.php"
UA = "NinjagoSiteMirror/1.0 (local mirror; category sort)"


def api_get(params: dict[str, str]) -> dict:
    q = urllib.parse.urlencode(params)
    url = f"{API}?{q}"
    proc = subprocess.run(
        ["curl", "-sS", "-L", "-A", UA, "--max-time", "45", url],
        capture_output=True,
        text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr or f"curl exit {proc.returncode}")
    return json.loads(proc.stdout)


def page_categories(title: str) -> list[str]:
    out: list[str] = []
    clcontinue: str | None = None
    while True:
        params = {
            "action": "query",
            "format": "json",
            "prop": "categories",
            "cllimit": "500",
            "titles": title,
        }
        if clcontinue:
            params["clcontinue"] = clcontinue
        data = api_get(params)
        pages = (data.get("query") or {}).get("pages") or {}
        for _, p in pages.items():
            for c in p.get("categories") or []:
                t = str(c.get("title") or "").strip()
                if t:
                    out.append(t)
        clcontinue = ((data.get("continue") or {}).get("clcontinue") or "").strip() or None
        if not clcontinue:
            break
    return sorted(set(out))


def norm_key(title: str) -> str:
    return " ".join(str(title or "").strip().lower().split())


def build_category_title_to_path(tree_root: dict) -> dict[str, str]:
    out: dict[str, str] = {}

    def walk(node: dict, parent_segs: list[str]) -> None:
        slug = str(node.get("slug") or "").strip()
        segs = parent_segs + ([slug] if slug else [])
        title = str(node.get("title") or "").strip()
        if title:
            out[norm_key(title)] = "/".join(segs)
        for ch in node.get("children") or []:
            if isinstance(ch, dict):
                walk(ch, segs)

    walk(tree_root, [])
    return out


def best_category_path_for_page_title(title: str, category_title_to_path: dict[str, str]) -> str | None:
    cats = page_categories(title)
    candidates: list[str] = []
    for cat in cats:
        p = category_title_to_path.get(norm_key(cat))
        if p:
            candidates.append(p)
    if not candidates:
        return None
    candidates.sort(key=lambda s: (-len([x for x in s.split("/") if x]), s))
    return candidates[0]


def save_manifest(path: Path, data: dict) -> None:
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def main() -> None:
    ap = argparse.ArgumentParser(description="Sort local _unsorted pages using Fandom categories.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--delay", type=float, default=0.08)
    ap.add_argument("--limit", type=int, default=0, help="Only process N unsorted rows")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()
    root = args.root.resolve()

    with open(root / "assets" / "data" / "wiki_pages.json", encoding="utf-8") as f:
        data = json.load(f)
    rows = list(data.get("pages") or [])
    tree = load_tree(root)
    category_title_to_path = build_category_title_to_path(tree)

    unsorted = [r for r in rows if str(r.get("categoryPath") or "").strip().lower() == "_unsorted"]
    if args.limit > 0:
        unsorted = unsorted[: args.limit]

    moved = 0
    updated = 0
    unresolved = 0
    missing = 0

    for i, row in enumerate(unsorted, start=1):
        title = str(row.get("wikiTitle") or row.get("display") or "").strip()
        slug = str(row.get("slug") or "").strip()
        if not title or not slug:
            unresolved += 1
            continue
        try:
            new_cat = best_category_path_for_page_title(title, category_title_to_path)
        except Exception as e:  # noqa: BLE001
            print(f"[{i}/{len(unsorted)}] API fail {slug}: {e}", file=sys.stderr, flush=True)
            unresolved += 1
            continue
        if not new_cat:
            unresolved += 1
            continue

        old_dir = root / "pages" / "_unsorted" / slug
        new_dir = root / "pages" / new_cat / slug
        row["categoryPath"] = new_cat
        row["href"] = f"/pages/{new_cat}/{slug}"
        updated += 1

        if old_dir.is_dir():
            if args.dry_run:
                print(f"MOVE {old_dir} -> {new_dir}", file=sys.stderr)
            else:
                new_dir.parent.mkdir(parents=True, exist_ok=True)
                if new_dir.exists():
                    shutil.rmtree(new_dir, ignore_errors=True)
                shutil.move(str(old_dir), str(new_dir))
            moved += 1
        else:
            missing += 1

        if args.delay > 0:
            time.sleep(args.delay)

    if not args.dry_run:
        data["pages"] = rows
        save_manifest(root / "assets" / "data" / "wiki_pages.json", data)

    print(
        f"{'DRY-RUN ' if args.dry_run else ''}updated={updated} moved={moved} unresolved={unresolved} missing_on_disk={missing}",
        file=sys.stderr,
        flush=True,
    )


if __name__ == "__main__":
    main()

