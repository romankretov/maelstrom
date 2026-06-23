# Maelstrom roadmap

Each phase delivers something usable. We never leave a phase half-done.

## Phase 0 — Foundation ✅ scaffolded

- Monorepo + Docker Compose for dev and prod
- FastAPI app with health, FastAPI-Users auth + TOTP + roles
- Append-only audit log (table + DB trigger)
- arq worker with a heartbeat task
- Next.js shell: login + dashboard skeleton with mobile sidebar
- Caddy reverse proxy, HTTPS via Let's Encrypt
- `bootstrap.sh` for VPS provisioning
- GH Actions: CI, image build to GHCR, manual SSH deploy with rollback

## Phase 1 — Data ingestion

- `connectors/` package: ccxt, yfinance, hyperliquid (live + historical)
- TimescaleDB hypertables for OHLCV (1m, 5m, 1h, 1d) + ticks
- Backfill jobs (worker) parametrised by symbol/timeframe/range
- Live WS streaming → Redis pub/sub → browser via FastAPI WebSocket
- `/markets` page: symbol search, live candle chart, recent trades

## Phase 2 — Strategy framework & backtesting

- `Strategy` base class with `on_bar`, `on_tick`, `on_order_fill` hooks
- Engine: `nautilus_trader`, same code path live and in backtest
- DB-versioned strategy storage
- In-browser Monaco editor with curated Python SDK
- Backtest UI: pick strategy + symbols + range → run on worker → metrics dashboard
- Walk-forward analysis, parameter sweeps (grid + random + optuna)

## Phase 3 — Paper trading & live execution

- `Broker` interface: `PaperBroker` (simulated fills on live data), `HyperliquidBroker` (real)
- Order lifecycle persisted + emitted on Redis
- Risk engine: position/drawdown/daily-loss limits, account kill switch
- Live mode gated: 2FA reauth + admin role + per-strategy toggle
- Reconciliation job: detect divergence from exchange every 30s
- Docker-per-strategy sandbox for AI-generated code

## Phase 4 — Portfolio & monitoring

- Equity curve (account + per-strategy)
- Open positions, recent fills, today P&L
- Slippage vs. backtest expectation; deviation alerts
- Performance attribution (per symbol, per hour, per regime)

## Phase 5 — AI

- `LLMRouter` for OpenAI + Anthropic with caching + cost tracking
- Strategy co-pilot: NL → code → diff → backtest
- Strategy optimizer: backtest+trades → parameter suggestions with rationale
- Opportunity scanner: structured market snapshot → ranked ideas → `/signals`
- Journal assistant: ask "why did X underperform?" with read access to strategy + trades + market

## Phase 6 — Notifications

- Telegram + Discord adapters via `NotificationRouter`
- Per-user, per-channel, per-event preferences with quiet hours
- Interactive bot commands: `/pause`, `/positions`, `/pnl today`

## Phase 7 — Production hardening

- Nightly encrypted backups → Backblaze B2
- Prometheus + Grafana + Loki for metrics/logs
- Alert rules → notification channels
- Recovery runbook + chaos drill
