#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"
LOG="$ROOT/wiki-sync.log"

exec > >(tee -a "$LOG") 2>&1

echo "=== Full wiki sync started $(date) ==="

# 1) Refresh Category:Content tree from Fandom (discover new page titles).
python3 -u scripts/fetch_fandom_content_category_tree.py \
  --no-sleep \
  --include-direct-pages \
  --max-depth 8 \
  --progress-every 50

# 2) Add any tree titles missing from wiki_pages.json manifest.
python3 scripts/merge_tree_titles_into_wiki_pages_manifest.py

# 3) Import pages that exist in manifest but not on disk yet.
python3 scripts/import_missing_wiki_pages_from_manifest.py --delay 0.08

# 4) Re-fetch every mirrored wiki page (update changed content).
python3 scripts/refresh_wiki_pages_from_manifest.py --delay 0.08

# 5) Re-fetch every character article.
python3 scripts/import_all_characters.py --force --delay 0.25

# 6) Rebuild routes, homepage search index, browse indexes, and sitemap.xml.
python3 scripts/build_site_routes.py

# 7) Point internal Fandom links to local mirrors.
python3 scripts/rewrite_fandom_character_links.py --apply

echo "=== Full wiki sync finished $(date) ==="
