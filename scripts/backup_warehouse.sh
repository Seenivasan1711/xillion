#!/usr/bin/env bash
# Snapshot the local backtest warehouse DB (bar/bar_coverage/
# option_chain_snapshot -- see Settings.backtest_database_url) to a single
# compressed file you can upload anywhere (Google Drive, etc.) and restore
# from later instead of re-running the hours-long NSE Bhavcopy backfill.
#
# Whole-file snapshot, not a per-table export: covers every table in the
# warehouse DB automatically, including any added after this script was
# written -- nothing to update here when the schema grows.
#
# Usage: ./scripts/backup_warehouse.sh [data_dir] [backup_dir]
# Restore with: ./scripts/restore_warehouse.sh <backup_file>
set -euo pipefail

DATA_DIR="${1:-./data}"
BACKUP_DIR="${2:-./data/backups/warehouse}"
DB_FILE="${DATA_DIR}/backtest_warehouse.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/warehouse_${TIMESTAMP}.db"

if [ ! -f "${DB_FILE}" ]; then
    echo "ERROR: warehouse database not found at ${DB_FILE}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

# SQLite's online backup API -- safe to run even while the app has the
# warehouse DB open (unlike a plain `cp`, which can copy a half-written
# page mid-write and produce a corrupt backup).
echo "Snapshotting ${DB_FILE}..."
sqlite3 "${DB_FILE}" ".backup '${BACKUP_FILE}'"
echo "Snapshot: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"

# gzip, not a raw .sql dump: a text SQL dump of millions of rows is far
# slower to generate/restore and larger on disk than compressing the
# binary file directly -- this is meant to be uploaded to Drive and
# restored quickly, not edited or diffed as text.
echo "Compressing..."
gzip -f "${BACKUP_FILE}"
echo "Done: ${BACKUP_FILE}.gz ($(du -h "${BACKUP_FILE}.gz" | cut -f1))"
echo ""
echo "Upload ${BACKUP_FILE}.gz wherever you keep backups (Drive, etc)."
echo "Restore later with: ./scripts/restore_warehouse.sh ${BACKUP_FILE}.gz"
