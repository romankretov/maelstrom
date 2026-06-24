#!/usr/bin/env bash
# restore.sh — restore Postgres from one of the local backup files.
# Run on the VPS as the deploy user.
#
# Usage:
#   restore.sh                         # picks the newest backup
#   restore.sh maelstrom-202606xxxxx.sql.gz   # restore a specific file
#
# This DROPs the existing schema and recreates it from the dump. The
# script asks for explicit yes-typing because it's destructive.

set -euo pipefail

cd "$(dirname "$0")/../.."

BACKUP_DIR="/opt/maelstrom/backups"
FILE="${1:-}"

if [[ -z "${FILE}" ]]; then
    FILE="$(ls -1t "${BACKUP_DIR}"/maelstrom-*.sql.gz 2>/dev/null | head -1 || true)"
fi
if [[ -z "${FILE}" || ! -f "${FILE}" ]]; then
    [[ "${FILE}" != /* ]] && FILE="${BACKUP_DIR}/${FILE}"
fi
if [[ ! -f "${FILE}" ]]; then
    echo "No backup file found at ${FILE}" >&2
    exit 1
fi

echo "About to RESTORE from: ${FILE}"
echo "This will DROP all existing tables in the live database."
read -rp "Type the exact filename to confirm: " confirm
if [[ "${confirm}" != "$(basename "${FILE}")" ]]; then
    echo "Aborted." >&2
    exit 2
fi

POSTGRES_USER="$(grep ^POSTGRES_USER .env | cut -d= -f2)"
POSTGRES_DB="$(grep ^POSTGRES_DB .env | cut -d= -f2)"

# 1. Stop services that hold connections
echo ">> stopping api + worker"
docker compose -f compose.prod.yml stop api worker

# 2. Drop and recreate public schema
echo ">> dropping public schema"
docker compose -f compose.prod.yml exec -T postgres \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}" -c \
    "DROP SCHEMA public CASCADE; CREATE SCHEMA public;"

# 3. Restore
echo ">> restoring"
gunzip -c "${FILE}" | docker compose -f compose.prod.yml exec -T postgres \
    psql -U "${POSTGRES_USER}" -d "${POSTGRES_DB}"

# 4. Restart services
echo ">> starting api + worker"
docker compose -f compose.prod.yml up -d api worker

echo "✅ restore complete."
