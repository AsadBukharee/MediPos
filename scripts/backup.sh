#!/bin/sh
# Daily compressed dump of the MediPos database. Run by the `backup` service in docker-compose.yml.
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"

STAMP=$(date +%Y%m%d-%H%M%S)
FILE="${BACKUP_DIR}/medipos-${STAMP}.dump"

pg_dump --host "${PGHOST:-db}" --username "${PGUSER:-medipos}" --format custom --file "${FILE}.tmp" "${PGDATABASE:-medipos}"
mv "${FILE}.tmp" "${FILE}"
echo "backup written: ${FILE}"

# Keep the last BACKUP_KEEP_DAYS days.
find "${BACKUP_DIR}" -name 'medipos-*.dump' -mtime "+${BACKUP_KEEP_DAYS:-14}" -delete
