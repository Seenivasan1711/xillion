#!/usr/bin/env bash
# Restore the local backtest warehouse DB from a backup made by
# scripts/backup_warehouse.sh (a .db.gz snapshot) -- e.g. after downloading
# one you'd previously uploaded to Drive, on a fresh machine or after
# losing the local file, instead of re-running the hours-long NSE Bhavcopy
# backfill.
#
# Usage: ./scripts/restore_warehouse.sh <backup_file.db.gz> [data_dir]
set -euo pipefail

BACKUP_FILE="${1:?Usage: $0 <backup_file.db.gz> [data_dir]}"
DATA_DIR="${2:-./data}"
DB_FILE="${DATA_DIR}/backtest_warehouse.db"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: backup file not found at ${BACKUP_FILE}" >&2
    exit 1
fi

mkdir -p "${DATA_DIR}"

if [ -f "${DB_FILE}" ]; then
    SAFETY="${DB_FILE}.before-restore.$(date +%Y%m%d_%H%M%S)"
    echo "Existing ${DB_FILE} found -- moving it to ${SAFETY} first (not deleting it)."
    mv "${DB_FILE}" "${SAFETY}"
fi

echo "Restoring ${BACKUP_FILE} -> ${DB_FILE}..."
if [[ "${BACKUP_FILE}" == *.gz ]]; then
    gunzip -c "${BACKUP_FILE}" > "${DB_FILE}"
else
    cp "${BACKUP_FILE}" "${DB_FILE}"
fi

echo "Restored: ${DB_FILE} ($(du -h "${DB_FILE}" | cut -f1))"
echo "Verifying..."
sqlite3 "${DB_FILE}" "SELECT 'bar: ' || count(*) FROM bar; SELECT 'bar_coverage: ' || count(*) FROM bar_coverage; SELECT 'option_chain_snapshot: ' || count(*) FROM option_chain_snapshot;"
echo "Done."
