#!/usr/bin/env bash
# Restore the XAUUSD research data from a backup made by
# scripts/backup_xauusd_research.sh (a .tar.gz snapshot) -- e.g. after
# downloading one you'd previously uploaded to Drive, on a fresh machine,
# instead of re-running the hours-long Dukascopy backfill.
#
# Usage: ./scripts/restore_xauusd_research.sh <backup_file.tar.gz> [data_dir]
set -euo pipefail

BACKUP_FILE="${1:?Usage: $0 <backup_file.tar.gz> [data_dir]}"
DATA_DIR="${2:-./research/xauusd_scalping/data/xauusd}"

if [ ! -f "${BACKUP_FILE}" ]; then
    echo "ERROR: backup file not found at ${BACKUP_FILE}" >&2
    exit 1
fi

if [ -d "${DATA_DIR}" ]; then
    SAFETY="${DATA_DIR}.before-restore.$(date +%Y%m%d_%H%M%S)"
    echo "Existing ${DATA_DIR} found -- moving it to ${SAFETY} first (not deleting it)."
    mv "${DATA_DIR}" "${SAFETY}"
fi

PARENT_DIR="$(dirname "${DATA_DIR}")"
mkdir -p "${PARENT_DIR}"

echo "Restoring ${BACKUP_FILE} -> ${DATA_DIR}..."
tar -xzf "${BACKUP_FILE}" -C "${PARENT_DIR}"

echo "Restored. Contents:"
find "${DATA_DIR}" -type f | sed 's/^/  /'
echo "Done."
