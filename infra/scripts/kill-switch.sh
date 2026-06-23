#!/usr/bin/env bash
# kill-switch.sh — halt all strategies + workers immediately.
# API + web stay up so you can investigate.
# Phase 3+ will wire this into a UI button as well.

set -euo pipefail

cd "$(dirname "$0")/../.."

echo "🛑  Pausing worker..."
docker compose -f compose.prod.yml stop worker

echo "🛑  Phase 3+: cancelling open orders via API kill endpoint (not yet implemented)."

echo "✅  Workers stopped. API + web still serving. Inspect logs with:"
echo "      docker compose -f compose.prod.yml logs --tail 200 -f"
