#!/bin/sh
# Proves a backup can be restored: loads the newest dump into a scratch database, checks it, drops it.
#   docker compose run --rm --entrypoint /scripts/restore-test.sh backup
set -eu

BACKUP_DIR="${BACKUP_DIR:-/backups}"

HOST="${PGHOST:-db}"
USER_NAME="${PGUSER:-medipos}"
LATEST=$(ls -1t "${BACKUP_DIR}"/medipos-*.dump 2>/dev/null | head -n 1 || true)
if [ -z "${LATEST}" ]; then
  echo "no backup found in ${BACKUP_DIR}" >&2
  exit 1
fi
SCRATCH="medipos_restore_test"

echo "restoring ${LATEST} into ${SCRATCH}"
dropdb --host "${HOST}" --username "${USER_NAME}" --if-exists "${SCRATCH}"
createdb --host "${HOST}" --username "${USER_NAME}" "${SCRATCH}"
pg_restore --host "${HOST}" --username "${USER_NAME}" --dbname "${SCRATCH}" --no-owner --exit-on-error "${LATEST}"

query() { psql --host "${HOST}" --username "${USER_NAME}" --dbname "$1" --tuples-only --no-align --command "$2"; }
for TABLE in inventory_stockmovement sales_sale accounting_journalline; do
  LIVE=$(query "${PGDATABASE:-medipos}" "select count(*) from ${TABLE}")
  RESTORED=$(query "${SCRATCH}" "select count(*) from ${TABLE}")
  echo "${TABLE}: restored ${RESTORED} rows (live now: ${LIVE})"
done
# The restored books must still balance.
BALANCE=$(query "${SCRATCH}" "select coalesce(sum(debit) - sum(credit), 0) from accounting_journalline")
dropdb --host "${HOST}" --username "${USER_NAME}" "${SCRATCH}"
case "${BALANCE}" in
  0|0.00) echo "restore test passed: ledger balances" ;;
  *) echo "restore test FAILED: ledger out of balance by ${BALANCE}" >&2; exit 1 ;;
esac
