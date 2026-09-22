#!/usr/bin/env bash
# Snapshot the XAUUSD research pipeline's downloaded M1 data
# (research/xauusd_scalping/data/xauusd/ -- partitioned monthly parquet
# files + the download manifest) to a single compressed archive you can
# upload anywhere (Google Drive, etc.) and restore from later, instead of
# re-running the hours-long Dukascopy backfill.
#
# Same "whole-directory snapshot, not per-file" spirit as
# backup_warehouse.sh's DB snapshot -- covers every parquet file
# automatically as more months are backfilled, nothing to update here.
#
# Note: if the backfill script (download_dukascopy.py) is actively running
# when you take this snapshot, the CURRENT month's parquet file may be
# mid-write. Safest to stop the backfill first, or accept that the most
# recent partial month might need re-backfilling after a restore -- every
# earlier month's file is already flushed and static.
#
# Usage: ./scripts/backup_xauusd_research.sh [data_dir] [backup_dir]
# Restore with: ./scripts/restore_xauusd_research.sh <backup_file>
set -euo pipefail

DATA_DIR="${1:-./research/xauusd_scalping/data/xauusd}"
BACKUP_DIR="${2:-./research/xauusd_scalping/data/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/xauusd_m1_${TIMESTAMP}.tar.gz"

if [ ! -d "${DATA_DIR}" ]; then
    echo "ERROR: data directory not found at ${DATA_DIR}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "Archiving ${DATA_DIR}..."
tar -czf "${BACKUP_FILE}" -C "$(dirname "${DATA_DIR}")" "$(basename "${DATA_DIR}")"
echo "Done: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"

echo ""
echo "Contents:"
tar -tzf "${BACKUP_FILE}" | grep -E '\.(parquet|json)$' | sed 's/^/  /'
echo ""
echo "Upload ${BACKUP_FILE} wherever you keep backups (Drive, etc)."
echo "Restore later with: ./scripts/restore_xauusd_research.sh ${BACKUP_FILE}"
