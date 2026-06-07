#!/usr/bin/env python3
"""
Build sitemap.xml (and grouped child sitemaps) for Google Search Console.

Scans on-disk index.html pages, assigns SEO metadata by section, and writes:
  - sitemap.xml          (sitemap index when split)
  - sitemap-core.xml     (home + hub pages)
  - sitemap-characters.xml
  - sitemap-wiki.xml

Configure the public origin in assets/data/sitemap_config.json or via --base-url.

  python3 scripts/build_sitemap.py
  python3 scripts/build_sitemap.py --base-url https://example.com/wiki
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import quote, urljoin, urlparse
from xml.sax.saxutils import escape

SCRIPT_DIR = Path(__file__).resolve().parent
ROOT = SCRIPT_DIR.parent
CONFIG = ROOT / "assets" / "data" / "sitemap_config.json"

SKIP_DIRS = {"assets", "server-files", "scripts", ".git"}


def load_config(path: Path) -> dict:
    if not path.is_file():
        return {"baseUrl": "https://example.com", "defaults": {"changefreq": "monthly", "priority": 0.5}}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def normalize_base_url(url: str) -> str:
    url = (url or "").strip().rstrip("/")
    if not url:
        raise ValueError("baseUrl is required")
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError(f"Invalid baseUrl: {url!r}")
    return url


def path_from_index(root: Path, index_file: Path) -> str:
    rel = index_file.parent.relative_to(root).as_posix()
    if rel == ".":
        return "/"
    return f"/{rel}"


def should_skip(root: Path, index_file: Path) -> bool:
    rel_parts = index_file.parent.relative_to(root).parts
    if not rel_parts:
        return False
    if rel_parts[0] in SKIP_DIRS:
        return True
    if index_file.name != "index.html":
        return True
    if rel_parts[0] == "404.html":
        return True
    return False


def discover_paths(root: Path) -> list[tuple[str, Path]]:
    rows: list[tuple[str, Path]] = []
    for index_file in sorted(root.rglob("index.html")):
        if should_skip(root, index_file):
            continue
        rows.append((path_from_index(root, index_file), index_file))
    return rows


def encode_loc(base_url: str, path: str) -> str:
    if path == "/":
        return f"{base_url}/"
    segments = path.strip("/").split("/")
    encoded = "/".join(quote(seg, safe=":@&=+$,;~*'()!") for seg in segments)
    return f"{base_url}/{encoded}"


def lastmod_iso(path: Path) -> str:
    ts = path.stat().st_mtime
    return datetime.fromtimestamp(ts, tz=timezone.utc).strftime("%Y-%m-%d")


def classify_path(path: str, groups: dict) -> str | None:
    for name, spec in groups.items():
        for pattern in spec.get("match") or []:
            if re.search(pattern, path):
                return name
    return None


def entry_xml(loc: str, lastmod: str, changefreq: str, priority: float) -> str:
    return (
        "  <url>\n"
        f"    <loc>{escape(loc)}</loc>\n"
        f"    <lastmod>{escape(lastmod)}</lastmod>\n"
        f"    <changefreq>{escape(changefreq)}</changefreq>\n"
        f"    <priority>{priority:.1f}</priority>\n"
        "  </url>\n"
    )


def write_urlset(path: Path, entries: list[str]) -> None:
    body = (
        '<?xml version="1.0" encoding="UTF-8"?>\n'
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(entries)
        + "</urlset>\n"
    )
    path.write_text(body, encoding="utf-8")


def write_index(path: Path, base_url: str, child_files: list[str]) -> None:
    lines = ['<?xml version="1.0" encoding="UTF-8"?>\n', '<sitemapindex xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n']
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    for name in child_files:
        loc = urljoin(f"{base_url}/", name)
        lines.append("  <sitemap>\n")
        lines.append(f"    <loc>{escape(loc)}</loc>\n")
        lines.append(f"    <lastmod>{today}</lastmod>\n")
        lines.append("  </sitemap>\n")
    lines.append("</sitemapindex>\n")
    path.write_text("".join(lines), encoding="utf-8")


def write_robots(root: Path, base_url: str) -> None:
    sitemap_loc = f"{base_url}/sitemap.xml"
    robots = (
        "User-agent: *\n"
        "Allow: /\n"
        "\n"
        f"Sitemap: {sitemap_loc}\n"
    )
    (root / "robots.txt").write_text(robots, encoding="utf-8")


def build_sitemap_files(
    root: Path | None = None,
    config: Path | None = None,
    base_url: str = "",
    *,
    write_robots_txt: bool = True,
) -> int:
    root = (root or ROOT).resolve()
    config_path = (config or CONFIG).resolve()
    cfg = load_config(config_path)
    resolved_base = normalize_base_url(base_url or cfg.get("baseUrl") or "")
    defaults = cfg.get("defaults") or {}
    default_changefreq = defaults.get("changefreq", "monthly")
    default_priority = float(defaults.get("priority", 0.5))
    groups: dict = cfg.get("groups") or {}

    discovered = discover_paths(root)
    if not discovered:
        print("No index.html pages found.", file=sys.stderr)
        return 0

    grouped_entries: dict[str, list[str]] = {name: [] for name in groups}
    grouped_entries["other"] = []
    home_entry: str | None = None

    for path, file_path in discovered:
        group = classify_path(path, groups) or "other"
        spec = groups.get(group) or {}
        changefreq = spec.get("changefreq", default_changefreq)
        priority = float(spec.get("priority", default_priority))
        if path == "/":
            priority = 1.0
            changefreq = "weekly"
        loc = encode_loc(resolved_base, path)
        entry = entry_xml(loc, lastmod_iso(file_path), changefreq, priority)
        if path == "/":
            home_entry = entry
            continue
        grouped_entries.setdefault(group, []).append(entry)

    if home_entry:
        grouped_entries.setdefault("core", [])
        grouped_entries["core"].insert(0, home_entry)

    child_files: list[str] = []
    url_counts: dict[str, int] = {}

    for name in ("core", "characters", "wiki", "other"):
        entries = grouped_entries.get(name) or []
        if not entries:
            continue
        if name == "other":
            filename = "sitemap-other.xml"
        else:
            filename = (groups.get(name) or {}).get("file") or f"sitemap-{name}.xml"
        out = root / filename
        write_urlset(out, entries)
        child_files.append(filename)
        url_counts[filename] = len(entries)

    index_path = root / "sitemap.xml"
    if len(child_files) == 1:
        (root / child_files[0]).replace(index_path)
        child_files = ["sitemap.xml"]
        url_counts = {"sitemap.xml": sum(url_counts.values())}
    else:
        write_index(index_path, resolved_base, child_files)

    if write_robots_txt:
        write_robots(root, resolved_base)

    total = sum(url_counts.values())
    print(f"Wrote sitemap for {total} URLs at {resolved_base}/", file=sys.stderr)
    for name, count in url_counts.items():
        print(f"  {name}: {count} URLs", file=sys.stderr)
    if write_robots_txt:
        print(f"Wrote robots.txt → Sitemap: {resolved_base}/sitemap.xml", file=sys.stderr)
    return total


def main() -> None:
    ap = argparse.ArgumentParser(description="Build SEO sitemap(s) for the static site.")
    ap.add_argument("--root", type=Path, default=ROOT)
    ap.add_argument("--config", type=Path, default=CONFIG)
    ap.add_argument("--base-url", default="", help="Override sitemap_config.json baseUrl")
    ap.add_argument("--no-robots", action="store_true", help="Do not rewrite robots.txt")
    args = ap.parse_args()

    total = build_sitemap_files(
        args.root,
        args.config,
        args.base_url,
        write_robots_txt=not args.no_robots,
    )
    if total == 0:
        sys.exit(1)


if __name__ == "__main__":
    main()
