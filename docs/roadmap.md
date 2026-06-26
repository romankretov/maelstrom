# Maelstrom roadmap

Each phase delivers something usable. Phases 0–7 are shipped; the "polish"
section at the bottom tracks the rolling stream of usability improvements
landed on top.

## Phase 0 — Foundation ✅

- Monorepo + Docker Compose for dev and prod
- FastAPI app with health, FastAPI-Users auth + TOTP + roles
- Append-only audit log (table + DB trigger)
- arq worker with a heartbeat task
- Next.js shell: login + dashboard skeleton with mobile sidebar
- Caddy reverse proxy, HTTPS via Let's Encrypt
- `bootstrap.sh` for VPS provisioning
- GH Actions: CI, image build to GHCR, manual SSH deploy with rollback

## Phase 1 — Data ingestion ✅

- `connectors/` package: ccxt (Binance) and Hyperliquid (live + historical)
- TimescaleDB hypertables for OHLCV (1m, 5m, 15m, 1h, 4h, 1d)
- Backfill jobs (worker) parametrised by symbol/timeframe/range
- Live WS streaming → Redis pub/sub → browser via FastAPI WebSocket
- `/markets` page: symbol search with autocomplete, live candle chart, sort by
  alpha / volume / 24h change, watchlist of pinned symbols

## Phase 2 — Strategy framework & backtesting ✅

- `Strategy` base class with `on_init` + `on_bar` hooks (see
  [`docs/strategy-sdk.md`](strategy-sdk.md))
- In-house engine — same code path runs in backtest and live, parity tests in
  `apps/worker/tests/test_sdk_parity.py`
- Sandboxed compile: `__import__` blocked, `Strategy`/`EngineBar`/`Position`/
  `math` injected as globals
- DB-versioned strategy storage with per-strategy notes, version diff dialog,
  clone, archive
- In-browser Monaco editor with the SDK reference inline, AI generate
  scaffold, dry-run button (24h slice, no persistence)
- Backtest UI: pick strategy + symbols + range + params via form fields (no
  JSON editing) → run on worker → metrics dashboard + equity chart + trades
  table + CSV export
- Parameter sweep with metric-vs-param curve view; compare overlay (up to 6
  runs)

## Phase 3 — Paper trading & live execution ✅

- `Broker` interface: `PaperBroker` (simulated fills on live data) +
  `HyperliquidBroker` (real, agent-wallet signing on testnet + mainnet)
- Order lifecycle persisted + emitted on Redis; `live_events` table backs the
  per-run event panel
- Risk engine: per-strategy notional cap, max position qty, account-level
  daily-loss kill switch, manual kill button
- Live mode gated: 2FA reauth + admin role + per-strategy toggle + mainnet
  flag (`MAELSTROM_ALLOW_MAINNET=1`)
- Reconciliation job: detects local-vs-exchange divergence every 5 minutes
- Shadow mode: route broker calls to `shadow_fills` instead of the exchange
  for safe canary runs

## Phase 4 — Portfolio & monitoring ✅

- Equity curve per account + per-strategy
- Open positions, recent fills (CSV exportable), realized + unrealized PnL
- PnL attribution per strategy
- Strategies overview surfaces live PnL + active run count per strategy
- Live event log per run with order/fill/reject/log events and tone-coded
  badges

## Phase 5 — AI ✅

- `LLMRouter` for OpenAI + Anthropic with caching + cost tracking + audit log
- Strategy co-pilot: NL → code (sandbox-safe by construction) → diff →
  backtest
- Strategy optimizer: backtest+trades → parameter suggestions with rationale,
  applies as a new version
- Opportunity scanner: structured market snapshot → ranked ideas →
  `/signals`, with per-signal one-click backtest scaffold, CSV export, and an
  editable system prompt
- Journal assistant: ask "why did X underperform?" with read access to
  strategy + trades + market

## Phase 6 — Notifications ✅

- Telegram + Discord adapters via per-channel dispatch
- Per-user, per-channel, per-event toggles with quiet hours
- Test-send button + event preview pane (render-time payload visible before
  enabling)
- Audit-logged sends and failures

## Phase 7 — Production hardening ✅

- Nightly encrypted pg_dump backups + optional rclone offsite (Backblaze B2)
- Restore script with explicit confirmation prompt
- Recovery runbook in [`docs/operations.md`](operations.md)
- Health page: 1m bar freshness, worker heartbeat, AI spend by purpose
- Setup checklist on the dashboard so new installs know what's left to wire

---

## Polish (ongoing)

Improvements landed on top of the seven-phase base:

- **`self.log()` SDK helper** — strategy-side debug messages surface in
  dry-run results and the live event panel.
- **Strategy notes** — persistent markdown per strategy, separate from version
  commit messages.
- **CSV exports** — trades, equity, fills, signals.
- **Responsive tables** — non-essential columns hide on sm/md breakpoints.
- **Sweep curve view** — auto-detects the varying parameter and plots it
  against any of six metrics.
- **Params as form fields** — regex-scans `self.params.get("name", default)`
  and renders typed inputs in the backtest dialog.
- **Account quick-switcher** — sidebar widget with localStorage-backed
  selection shared across pages.
- **Notification preview** — see exactly what each event will look like in
  Telegram or Discord before enabling.

See `git log` for the per-commit detail.
