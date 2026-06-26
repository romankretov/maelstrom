# Maelstrom

Personal quant trading suite. Ingests data via ccxt, trades live on Hyperliquid,
backtests strategies with an in-house engine, uses OpenAI + Anthropic for
strategy generation and signal scanning, and ships notifications via Telegram
and Discord.

Designed to run on a single VPS, with a web UI usable on both laptop and phone.

**Status:** all seven phases shipped — auth, data ingestion, strategy editor +
backtests, paper and Hyperliquid live trading, AI co-pilot + scanner +
optimizer, notifications, backups + restore. See [`docs/roadmap.md`](docs/roadmap.md)
for the per-phase breakdown.

---

## Stack

- **API:** FastAPI + FastAPI-Users + SQLAlchemy 2 + asyncpg + Pydantic v2
- **Worker:** arq (Redis-backed) for ingest, backtests, live runners, AI tasks
- **Web:** Next.js 15 (App Router) + React 19 + Tailwind + shadcn/ui + Monaco editor + lightweight-charts + SWR
- **Data:** Postgres 16 + TimescaleDB hypertables, Redis 7
- **Engine:** in-house Python strategy SDK (sandboxed) — same code runs in backtest and live
- **Exchanges:** ccxt.pro for Binance + Hyperliquid; HL agent-wallet signing for live trading
- **AI:** Anthropic (Claude 4.x) + OpenAI SDKs, encrypted keys at rest, audit-logged calls
- **Reverse proxy:** Caddy with auto Let's Encrypt
- **Container:** Docker Compose, images in GHCR
- **CI/CD:** GitHub Actions → GHCR → SSH-deploy to VPS, with healthcheck-gated rollback
- **Backups:** pg_dump → local + optional rclone offsite

## Prerequisites (local dev)

- Docker + Compose plugin (24+)
- Python 3.12 + [`uv`](https://github.com/astral-sh/uv) (optional, only for non-container linting)
- Node 22 + npm (optional, only for non-container linting)
- `make`, `gh` (GitHub CLI for deploy commands)

## Quickstart — local dev

```bash
git clone https://github.com/romankretov/maelstrom.git
cd maelstrom
cp .env.example .env       # generated automatically on first `make dev` if absent
make dev                   # starts postgres, redis, api, worker, web with hot reload
```

Then open <http://localhost:3000>. The API is at <http://localhost:8000>, OpenAPI
docs at <http://localhost:8000/docs>.

On first boot, run migrations and create yourself a user via the web UI's
`/setup` screen (or, equivalently):

```bash
make migrate
curl -X POST http://localhost:8000/auth/register \
     -H 'Content-Type: application/json' \
     -d '{"email":"you@example.com","password":"<strong-password>"}'
make shell-db
# then in psql:
UPDATE users SET role='admin', is_superuser=true, is_verified=true
 WHERE email='you@example.com';
```

## Useful commands

```bash
make            # list available targets
make dev        # start everything
make logs S=api # tail one service
make test       # run all tests
make typecheck  # mypy + tsc
make precheck   # lint + format + typecheck across api/worker/web
make migrate-new M="add strategies table"
make deploy TAG=main
```

## Feature surface

- **Markets:** symbol catalog (sortable by volume / 24h change / alpha), live
  candles, watchlist of pinned symbols.
- **Research:** correlation matrix, funding-rate history, realized vol stats.
- **Strategies:** Monaco editor with the SDK reference inline, AI-generate
  scaffold, version diff, persistent notes per strategy, dry-run before
  saving.
- **Backtesting:** auto-backfill missing bars, parameter sweep with a
  metric-vs-param curve view, compare overlay (up to 6 runs), CSV export of
  trades and equity.
- **Live trading:** paper accounts + Hyperliquid testnet + mainnet (gated
  behind a separate env flag), per-strategy notional caps, daily-loss kill
  switch, reconciliation against the exchange every 5 minutes.
- **AI:** strategy generation, strategy optimizer (post-backtest), opportunity
  scanner (cron), journal assistant — all audit-logged with token/cost
  tracking and prompt caching.
- **Notifications:** Telegram + Discord channels with per-event toggles, quiet
  hours, and a preview pane so you know what each event looks like before
  enabling it.
- **Ops:** dashboard with setup checklist + health metrics, append-only audit
  log, encrypted secrets, scheduled pg_dump backups, restore script.

## Production deployment

### One-time VPS bootstrap

On a fresh Ubuntu 24.04 VPS (we recommend Hostinger KVM 4 or larger):

```bash
ssh root@<your-vps-ip>
curl -fsSL https://raw.githubusercontent.com/romankretov/maelstrom/main/infra/bootstrap.sh \
    | bash -s -- \
        --ssh-key "ssh-ed25519 AAAA... your@laptop" \
        --repo romankretov/maelstrom \
        --domain maelstromhub.com
```

This:
- creates a `deploy` user with sudo + your SSH key
- locks down SSH (key-only, no root, no password)
- installs Docker, configures UFW + fail2ban + unattended-upgrades
- adds a 4 GB swapfile
- generates `/etc/maelstrom/master.key` (used to encrypt exchange API keys, LLM
  keys, and notification secrets at rest — **back this up**)
- clones the repo to `/opt/maelstrom`
- writes a `.env` with generated DB password + API secret

### GitHub Actions secrets

Set these at `https://github.com/romankretov/maelstrom/settings/secrets/actions`:

| Secret              | Value                                              |
| ------------------- | -------------------------------------------------- |
| `DEPLOY_HOST`       | VPS IP or `maelstromhub.com`                       |
| `DEPLOY_USER`       | `deploy`                                           |
| `DEPLOY_SSH_KEY`    | private key matching the public key in `bootstrap` |
| `DEPLOY_KNOWN_HOSTS`| `ssh-keyscan -H <vps-ip>` output                   |

### First deploy

Push to `main`. Then:

1. Wait for the **Build & Push Images** workflow to finish.
2. Go to Actions → **Deploy** → "Run workflow" → image_tag = `main`.
3. Watch it run. The workflow runs migrations, restarts services, and rolls back if
   the healthcheck fails.

Once it's green, hit `https://maelstromhub.com/`. Register the first user via the
API (see Quickstart above) and elevate to admin in psql.

### Adding a live Hyperliquid account

See [`docs/operations.md`](docs/operations.md#adding-a-hyperliquid-account-end-to-end)
for the master-vs-agent wallet flow. Mainnet is gated behind
`MAELSTROM_ALLOW_MAINNET=1` in `.env` — testnet first, always.

## Repo layout

```
apps/
  api/        FastAPI app (auth, routes, schemas, alembic migrations)
  worker/     arq workers (ingest, backtests, live runners, AI tasks, notify)
  web/        Next.js frontend
packages/
  connectors/ ccxt / hyperliquid adapters (live + historical)
  strategies/ strategy SDK exposed to user code
  shared/     Pydantic models <-> TS types
infra/
  caddy/      reverse proxy config
  scripts/    healthcheck, rollback, restore, kill-switch
  bootstrap.sh
docs/
  roadmap.md       phase-by-phase plan + status
  operations.md    runbook: deploys, HL onboarding, backup/restore, emergency
  strategy-sdk.md  authoritative SDK contract for user strategies
  test-backlog.md  manual verification checklist per feature area
.github/workflows/
  ci.yml      PR + main checks (lint, type, test, docker smoke)
  build.yml   Push images to GHCR on main
  deploy.yml  Manual deploy to VPS (or on git tag v*)
compose.dev.yml   Local dev with hot reload
compose.prod.yml  Production (uses GHCR images)
```

## Security baseline

- HTTPS via Caddy + Let's Encrypt (auto-renewing)
- Login: password (Argon2) + TOTP for sensitive ops
- SSH key-only, root disabled, password auth disabled, fail2ban
- UFW: 22, 80, 443 only
- Exchange API keys, LLM keys, and Telegram bot tokens: stored encrypted in DB
  with `pynacl` SecretBox; master key in `/etc/maelstrom/master.key` (root:root, 0400)
- User-written strategy code runs sandboxed — `__import__` is blocked, only the
  SDK + `math` are injected as globals
- Audit log: append-only Postgres table + DB trigger refusing UPDATE/DELETE
- LLMs receive only sanitized snapshots; never raw API keys

## License

MIT — see [LICENSE](./LICENSE).
