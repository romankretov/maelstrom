#!/bin/bash
# Maelstrom Postgres backup daemon.
#
# Loops forever. Once per BACKUP_INTERVAL (default 24h) it:
#   1. pg_dump --format=custom + gzip -> /backups/maelstrom-<utc>.sql.gz
#   2. enforces a retention window (RETENTION_DAYS, default 14)
#   3. (optional) rclone copy to $RCLONE_REMOTE_PATH for offsite backup
#
# Env vars (all overridable in compose.prod.yml):
#   POSTGRES_HOST           default: postgres
#   POSTGRES_PORT           default: 5432
#   POSTGRES_USER           required
#   POSTGRES_PASSWORD       required (passed in via env_file)
#   POSTGRES_DB             required
#   BACKUP_INTERVAL         seconds; default: 86400
#   RETENTION_DAYS          default: 14
#   RCLONE_REMOTE_PATH      e.g. "b2:my-bucket/maelstrom" (empty = local only)
#   RCLONE_CONFIG_BASE64    base64-encoded rclone.conf contents (optional)

set -euo pipefail

: "${POSTGRES_HOST:=postgres}"
: "${POSTGRES_PORT:=5432}"
: "${POSTGRES_USER:?POSTGRES_USER must be set}"
: "${POSTGRES_PASSWORD:?POSTGRES_PASSWORD must be set}"
: "${POSTGRES_DB:?POSTGRES_DB must be set}"
: "${BACKUP_INTERVAL:=86400}"
: "${RETENTION_DAYS:=14}"
: "${RCLONE_REMOTE_PATH:=}"
: "${RCLONE_CONFIG_BASE64:=}"

mkdir -p /backups

# Materialize the rclone config from env (so we don't have to bind-mount a
# config file on the VPS).
if [[ -n "${RCLONE_CONFIG_BASE64}" ]]; then
    mkdir -p /root/.config/rclone
    echo "${RCLONE_CONFIG_BASE64}" | base64 -d > /root/.config/rclone/rclone.conf
    chmod 0600 /root/.config/rclone/rclone.conf
fi

log() { printf '[backup %s] %s\n' "$(date -u +%FT%TZ)" "$*"; }

backup_once() {
    local ts file
    ts="$(date -u +%Y%m%dT%H%M%SZ)"
    file="/backups/maelstrom-${ts}.sql.gz"
    log "starting dump -> ${file}"
    PGPASSWORD="${POSTGRES_PASSWORD}" \
        pg_dump \
            --host "${POSTGRES_HOST}" \
            --port "${POSTGRES_PORT}" \
            --username "${POSTGRES_USER}" \
            --dbname "${POSTGRES_DB}" \
            --format=plain \
            --no-owner \
            --no-privileges \
        | gzip --best > "${file}.tmp"
    mv "${file}.tmp" "${file}"
    local size
    size="$(du -h "${file}" | cut -f1)"
    log "done. size=${size}"

    if [[ -n "${RCLONE_REMOTE_PATH}" ]]; then
        log "rclone copy -> ${RCLONE_REMOTE_PATH}"
        if rclone copy --quiet "${file}" "${RCLONE_REMOTE_PATH}/"; then
            log "rclone OK"
        else
            log "WARN rclone copy failed"
        fi
    fi

    # Retention pruning (local only — remote retention is rclone's problem)
    find /backups -name 'maelstrom-*.sql.gz' -type f -mtime "+${RETENTION_DAYS}" -delete -print \
        | while read -r removed; do log "pruned ${removed}"; done
}

log "starting; interval=${BACKUP_INTERVAL}s retention=${RETENTION_DAYS}d remote=${RCLONE_REMOTE_PATH:-none}"
while :; do
    if ! backup_once; then
        log "ERROR backup_once failed; will retry next cycle"
    fi
    log "sleeping ${BACKUP_INTERVAL}s"
    sleep "${BACKUP_INTERVAL}"
done
