# Maelstrom

Personal quant trading suite. Ingests data via ccxt/yfinance, trades on Hyperliquid,
backtests strategies with nautilus_trader, uses OpenAI + Anthropic for strategy
generation and signal scanning, and ships notifications via Telegram and Discord.

Designed to run on a single VPS, with a web UI usable on both laptop and phone.

**Status:** Phase 0 — foundation scaffold. Auth, dashboard shell, deploy pipeline.
The rest of the suite lands phase by phase. See [`docs/roadmap.md`](docs/roadmap.md).

---

## Stack

- **API:** FastAPI + FastAPI-Users + SQLAlchemy 2 + asyncpg + Pydantic v2
- **Worker:** arq (Redis-backed) for ingest, backtests, live strategies
- **Web:** Next.js 15 (App Router) + React 19 + Tailwind + shadcn/ui + Recharts + lightweight-charts
- **Data:** Postgres 16 + TimescaleDB hypertables, Redis 7
- **Reverse proxy:** Caddy with auto Let's Encrypt
- **Container:** Docker Compose, images in GHCR
- **CI/CD:** GitHub Actions → GHCR → SSH-deploy to VPS

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

On first boot, run migrations and create yourself a user:

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
make migrate-new M="add strategies table"
make deploy TAG=main
```

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
- generates `/etc/maelstrom/master.key` (used to encrypt exchange API keys at rest — **back this up**)
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

## Repo layout

```
apps/
  api/        FastAPI app
  worker/     arq workers
  web/        Next.js frontend
packages/
  connectors/ ccxt / yfinance / hyperliquid adapters (Phase 1+)
  strategies/ strategy SDK exposed to user code (Phase 2+)
  shared/     Pydantic models <-> TS types (Phase 1+)
infra/
  caddy/      reverse proxy config
  scripts/    healthcheck, rollback, kill-switch
  bootstrap.sh
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
- Exchange API keys: stored encrypted in DB with `pynacl` SecretBox; master key in `/etc/maelstrom/master.key` (root:root, 0400)
- Audit log: append-only Postgres table + DB trigger refusing UPDATE/DELETE
- LLMs receive only sanitized snapshots; never raw API keys

## License

MIT — see [LICENSE](./LICENSE).
