#!/bin/sh
# Automated daily PostgreSQL dump (AD-10). Retention period is explicitly
# deferred (PRD Open Question #9) — this writes dumps only, it never deletes
# old ones. /backups is expected to be a volume mounted to off-host storage;
# the concrete off-host mechanism is a hosting-provider decision (deferred).
set -eu

mkdir -p /backups

while true; do
    timestamp=$(date -u +%Y%m%dT%H%M%SZ)
    dest="/backups/${POSTGRES_DB}_${timestamp}.sql.gz"
    echo "[backup] dumping ${POSTGRES_DB} to ${dest}"
    pg_dump --host postgres --username "$POSTGRES_MIGRATOR_USER" --dbname "$POSTGRES_DB" \
        | gzip > "$dest"
    echo "[backup] done: ${dest}"
    sleep 86400
done
