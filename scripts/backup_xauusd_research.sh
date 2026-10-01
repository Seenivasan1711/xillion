#!/usr/bin/env bash
# Snapshot the research pipeline's downloaded/imported market data
# (research/xauusd_scalping/data/ -- XAUUSD + EURUSD Dukascopy M1 parquet,
# imported MT5 broker history, download manifests) to a single compressed
# archive you can upload anywhere (Google Drive, etc.) and restore from
# later, instead of re-running the hours-long Dukascopy backfill or losing
# the imported MT5 history entirely (it isn't re-downloadable the way the
# Dukascopy data is).
#
# Archives the whole data/ directory (minus backups/ itself and
# __pycache__), not just one instrument's subfolder -- covers every data
# source added later (new pairs, new MT5 exports) automatically, nothing
# to update here as more get added. (Before 2026-10-01 this only archived
# data/xauusd/ and silently missed data/eurusd/ and the imported
# data/xauusd_mt5*/ directories -- fixed because a new-machine restore from
# the old backup would have lost both without any error.)
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

DATA_DIR="${1:-./research/xauusd_scalping/data}"
BACKUP_DIR="${2:-${DATA_DIR}/backups}"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/xauusd_research_${TIMESTAMP}.tar.gz"

if [ ! -d "${DATA_DIR}" ]; then
    echo "ERROR: data directory not found at ${DATA_DIR}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

echo "Archiving ${DATA_DIR}..."
tar -czf "${BACKUP_FILE}" \
    -C "$(dirname "${DATA_DIR}")" \
    --exclude="$(basename "${DATA_DIR}")/backups" \
    --exclude="__pycache__" \
    "$(basename "${DATA_DIR}")"
echo "Done: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"

echo ""
echo "Contents (top-level dirs):"
tar -tzf "${BACKUP_FILE}" | awk -F/ 'NF>1 {print $1"/"$2}' | sort -u | sed 's/^/  /'
echo ""
echo "Upload ${BACKUP_FILE} wherever you keep backups (Drive, etc)."
echo "Restore later with: ./scripts/restore_xauusd_research.sh ${BACKUP_FILE}"
