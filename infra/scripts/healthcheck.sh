#!/usr/bin/env bash
# healthcheck.sh — block until the stack is healthy (or fail).
# Used by deploy.yml after `docker compose up -d`.

set -euo pipefail

DOMAIN="${1:-${MAELSTROM_DOMAIN:-localhost}}"
TIMEOUT="${2:-180}"   # seconds
INTERVAL=3
deadline=$(( $(date +%s) + TIMEOUT ))

check_url() {
    local url="$1"
    curl -fsS --max-time 5 "$url" >/dev/null
}

echo "Waiting up to ${TIMEOUT}s for https://${DOMAIN}/api/healthz ..."
while (( $(date +%s) < deadline )); do
    if check_url "https://${DOMAIN}/api/healthz"; then
        echo "✅  API healthy."
        # Also smoke the web frontend.
        if check_url "https://${DOMAIN}/login"; then
            echo "✅  Web healthy."
            exit 0
        fi
    fi
    sleep "${INTERVAL}"
done

echo "❌  Healthcheck timed out after ${TIMEOUT}s." >&2
docker compose -f compose.prod.yml ps >&2 || true
exit 1
