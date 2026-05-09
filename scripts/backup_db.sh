#!/usr/bin/env bash
# Daily SQLite backup — keep 30 days of snapshots.
# Usage: ./scripts/backup_db.sh [data_dir] [backup_dir]
set -euo pipefail

DATA_DIR="${1:-./data}"
BACKUP_DIR="${2:-./data/backups}"
DB_FILE="${DATA_DIR}/xillion.db"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="${BACKUP_DIR}/xillion_${TIMESTAMP}.db"
KEEP_DAYS=30

if [ ! -f "${DB_FILE}" ]; then
    echo "ERROR: database not found at ${DB_FILE}" >&2
    exit 1
fi

mkdir -p "${BACKUP_DIR}"

# Use SQLite's online backup API (safe with concurrent readers/writers)
sqlite3 "${DB_FILE}" ".backup '${BACKUP_FILE}'"

echo "Backup written: ${BACKUP_FILE} ($(du -h "${BACKUP_FILE}" | cut -f1))"

# Prune old backups
find "${BACKUP_DIR}" -name "xillion_*.db" -mtime "+${KEEP_DAYS}" -delete
echo "Old backups pruned (>${KEEP_DAYS} days)"
