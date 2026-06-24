# Maelstrom — test backlog

Things to verify before relying on them. Tick as you go.

## Phase 3.2 — risk engine + kill switch (untested)

- [ ] Migration `0005_risk` runs cleanly on the existing DB. Verify with:
      `\d accounts` (should show `killed`, `daily_loss_limit_pct`) and
      `\d live_strategies` (should show `max_notional_per_symbol`, `max_position_qty`).
- [ ] **Kill account button** on `/portfolio` flips the banner red within a couple of seconds.
      All running live strategies for that account transition `running` → `pending_stop` → `stopped`
      within ~3s (the LiveManager poll).
- [ ] **Killed account rejects new orders.** Try `Run live` while killed — POST returns 409.
- [ ] **Unkill** (admin only): banner clears, you can start strategies again.
- [ ] **Per-strategy size cap.** Run live with `max_notional_per_symbol = 100`. Once the strategy
      tries to open a position notional > $100, the order shows up in `/portfolio` Recent fills as a
      `rejected` row with the reason. (Reason includes `would exceed max_notional_per_symbol`.)
- [ ] **Daily loss limit.** Set `daily_loss_limit_pct = 0.01` on a paper account via
      `PATCH /accounts/{id}` (curl), force a few losing trades, confirm new orders get rejected
      with `daily loss limit breached`. Limit resets at UTC midnight.

## Phase 3.3 — Hyperliquid broker + recon (untested, this push)

> ⚠️ Test these on **Hyperliquid testnet first**. Mainnet is gated behind a second flag.

- [ ] **Create a live testnet account** (admin only):
      ```
      curl -X POST .../api/accounts -H "Authorization: Bearer $TOKEN" \
        -H "Content-Type: application/json" \
        -d '{"name":"hl-testnet","kind":"live_hl_testnet","starting_capital":"1000"}'
      ```
- [ ] **Attach Hyperliquid credentials** via UI on `/portfolio`. Wallet address + private key from
      a *testnet* Hyperliquid agent wallet. Confirm:
        - Private key is **not** returned by `GET /accounts/{id}`.
        - DB shows `api_key_enc` populated (non-null `bytea`) and `meta.wallet_address` set.
        - Master key at `/etc/maelstrom/master.key` is unchanged and still 32 bytes.
- [ ] **Run live on testnet account.** Submit a small order via a hand-crafted strategy that
      issues exactly one `self.buy(symbol, notional=10)` on `BTC-PERP`. Verify:
        - Order lands in `/portfolio` recent fills.
        - Order appears in your Hyperliquid testnet UI / API too.
        - Local position matches what the exchange shows.
- [ ] **Reconciliation job.** Worker logs show `reconcile.ok` every 5 minutes per live account.
      Force a mismatch (manually open a position on Hyperliquid outside the bot, wait a tick):
      worker should log `reconcile.mismatch` with details.
- [ ] **Mainnet guardrail.** Try to create `kind=live_hl_main` *without* `MAELSTROM_ALLOW_MAINNET=1`
      set on the VPS — API should refuse with 403.

## Phase 3.0–3.1 — re-verifications worth doing once

- [ ] `/portfolio` numbers tie out after a few fills. Cash + position_value should ≈ equity (within
      sum of fees). Realized + unrealized PnL should equal total PnL (final equity − starting).
- [ ] Stop button on Live runs: row flips `running` → `pending_stop` → `stopped` within ~3s.
- [ ] Worker restart preserves live strategies: anything `running` gets re-spawned from
      `pending_start` via `LiveManager._resume_orphans()`.
- [ ] Restart preserves paper positions (they live in Postgres, but verify after a deploy).

## Phase 5.0+5.1 — LLM router + strategy co-pilot (untested)

- [ ] Migration `0006_llm` runs cleanly. Tables `llm_providers` and `llm_calls` exist.
- [ ] Anthropic + OpenAI Python SDKs installed in the api image
      (`pip list | grep -E 'anthropic|openai'`).
- [ ] **Settings page** (`/settings`): each provider card shows "no key" pill initially. Paste
      your Anthropic key → save → pill flips to "key set". Same for OpenAI.
- [ ] Default model auto-fills from `MODEL_OPTIONS` or you can type a custom one.
- [ ] **AI Generate dialog** on `/strategies/new` and `/strategies/[id]`: prompt like
      "momentum strategy on ETH-PERP, breakout above 30-bar high, exit on 10-bar low, $5k notional"
      should return runnable code that backtests without `EngineError`.
- [ ] `/ai/calls` returns the audit row(s): tokens, cost, duration, purpose=strategy_gen.
- [ ] Prompt caching works for Anthropic — on the second generation in the same hour, you should
      see `cached_tokens > 0` and a lower `cost_usd` than the first call.
- [ ] **OpenAI key is encrypted at rest.** Verify via psql:
      `SELECT name, length(api_key_enc) FROM llm_providers;` — non-null length, but the key shouldn't
      be visible in plaintext anywhere in `audit_log` either.
- [ ] Disabling a provider (toggle) blocks further calls with a clean 400.

## Phase 1–2 — re-verifications worth doing once

- [ ] CCXT instrument sync still produces ~200 Binance + ~150 Hyperliquid perps after deploys.
- [ ] Backfill 7d on BTC-PERP 1h completes in <30s.
- [ ] Backtest of `sma-cross-btc` over 1y of 1h bars: metrics + equity chart + trades render.
- [ ] Live 1m streams still publishing — check `/markets` BTC-PERP shows the green `live` dot and a
      ticking last price.

## Ops / safety

- [ ] **Backup `/etc/maelstrom/master.key`.** If you lose it, every encrypted exchange key in
      `accounts.api_key_enc` becomes irrecoverable. `base64 < /etc/maelstrom/master.key` →
      paste into 1Password or wherever.
- [ ] Kill switch script (`infra/scripts/kill-switch.sh`) stops workers cleanly. Try it once on the
      VPS so you've used it before the day you need to.
- [ ] Outage drill: stop postgres for 30s, then start it. API + worker should reconnect cleanly,
      live strategies recover from the next bar.
