#!/usr/bin/env bash
set -euo pipefail

SOURCE_DIR="/Users/evan/Downloads/ninjago site"
DEST_DIR="/Users/evan/Downloads/ninjagowiki"

if [[ ! -d "$SOURCE_DIR" ]]; then
  echo "Source folder not found: $SOURCE_DIR" >&2
  exit 1
fi

if [[ ! -d "$DEST_DIR" ]]; then
  echo "Destination folder not found: $DEST_DIR" >&2
  exit 1
fi

echo "Overwriting destination with source..."
echo "  FROM: $SOURCE_DIR"
echo "  TO:   $DEST_DIR"
echo

# Overwrite existing files from source, but keep destination-only extras.
rsync -a "$SOURCE_DIR"/ "$DEST_DIR"/

echo "Done. '$DEST_DIR' now matches '$SOURCE_DIR'."
