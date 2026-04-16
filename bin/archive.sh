#!/bin/bash
# A2: Data archival — compress old JSONL files, move ancient data.
# Usage: ./bin/archive.sh [--dry-run]
# Compresses sources > 90 days old, moves > 365 days to data/archive/

set -e
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
DATA_DIR="${MARKET_INTEL_DATA_DIR:-$PROJECT_DIR/data}"
ARCHIVE_DIR="$DATA_DIR/archive"
DRY="${1:-}"
CUTOFF_90=$(date -d "-90 days" +%Y-%m-%d 2>/dev/null || date -v-90d +%Y-%m-%d 2>/dev/null || echo "2026-01-01")
CUTOFF_365=$(date -d "-365 days" +%Y-%m-%d 2>/dev/null || date -v-365d +%Y-%m-%d 2>/dev/null || echo "2025-04-15")

compressed=0
archived=0

for category_dir in "$DATA_DIR"/sources/*/; do
    [ -d "$category_dir" ] || continue
    for day_dir in "$category_dir"*/; do
        [ -d "$day_dir" ] || continue
        dir_name=$(basename "$day_dir")
        date_part="${dir_name%%_*}"  # extract YYYY-MM-DD from YYYY-MM-DD_slot

        # Skip if date can't be parsed
        [[ "$date_part" =~ ^[0-9]{4}-[0-9]{2}-[0-9]{2}$ ]] || continue

        # > 365 days: move to archive
        if [[ "$date_part" < "$CUTOFF_365" ]]; then
            rel_path="${day_dir#$DATA_DIR/sources/}"
            target="$ARCHIVE_DIR/sources/$rel_path"
            if [ "$DRY" = "--dry-run" ]; then
                echo "[dry] archive: $day_dir → $target"
            else
                mkdir -p "$(dirname "$target")"
                mv "$day_dir" "$target"
            fi
            archived=$((archived + 1))
            continue
        fi

        # > 90 days: compress JSONL files
        if [[ "$date_part" < "$CUTOFF_90" ]]; then
            for jsonl in "$day_dir"*.jsonl; do
                [ -f "$jsonl" ] || continue
                [ -f "${jsonl}.gz" ] && continue  # already compressed
                if [ "$DRY" = "--dry-run" ]; then
                    echo "[dry] compress: $jsonl"
                else
                    gzip "$jsonl"
                fi
                compressed=$((compressed + 1))
            done
        fi
    done
done

echo "Done. Compressed: $compressed files. Archived: $archived directories."
