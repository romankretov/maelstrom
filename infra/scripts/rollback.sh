#!/usr/bin/env bash
# rollback.sh — restore the previous image tag and bring the stack back up.

set -euo pipefail

cd "$(dirname "$0")/../.."

if [[ ! -f .image-tag.bak ]]; then
    echo "No .image-tag.bak — nothing to roll back to." >&2
    exit 1
fi

PREV_TAG="$(cat .image-tag.bak)"
echo "Rolling back to image tag: ${PREV_TAG}"
mv -f .image-tag.bak .image-tag
sed -i "s|^IMAGE_TAG=.*|IMAGE_TAG=${PREV_TAG}|" .env
docker compose -f compose.prod.yml pull
docker compose -f compose.prod.yml up -d --remove-orphans
./infra/scripts/healthcheck.sh
