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
    tmp="${dest%.gz}"
    echo "[backup] dumping ${POSTGRES_DB} to ${dest}"
    # Dump to a plain file and check pg_dump's own exit status directly:
    # `pg_dump | gzip > dest` would mask a pg_dump failure, since a plain
    # `sh` pipeline's exit status is gzip's (the last command), not
    # pg_dump's — a dead/unreachable postgres would still "succeed".
    if pg_dump --host postgres --username "$POSTGRES_BACKUP_USER" --dbname "$POSTGRES_DB" > "$tmp" \
        && gzip -f "$tmp"; then
        date -u +%s > /backups/.last_success
        echo "[backup] done: ${dest}"
    else
        echo "[backup] FAILED to back up ${POSTGRES_DB}" >&2
        rm -f "$tmp" "$dest"
    fi
    sleep 86400
done
