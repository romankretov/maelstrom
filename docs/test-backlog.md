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

## Phase 6 — notifications (untested)

- [ ] Migration `0008_notifications` runs cleanly.
- [ ] **Telegram path:**
      - Create a bot via @BotFather, copy the token.
      - Message @userinfobot on Telegram for your chat_id.
      - In `/settings` → Notifications → Add channel → Telegram → label,
        chat_id, bot token → Save.
      - Click **Test** on the row → message arrives in Telegram in <5s.
- [ ] **Discord path:**
      - In a Discord server, channel settings → Integrations → Webhooks → New.
      - Copy webhook URL.
      - Add channel in UI → Discord → webhook URL → Save → Test → message lands.
- [ ] Toggle event chips on the channel row; only enabled events fire.
- [ ] Disable (red pill) blocks all sends until re-enabled.
- [ ] Quiet hours: not yet UI-editable; verify via API PATCH that
      `quiet_start=22:00 quiet_end=07:00` suppresses sends during that
      window and logs `notify` task return status=`quiet_hours`.
- [ ] Worker log shows `notify.sent kind=telegram event=test` on test.
- [ ] No plaintext bot token in any audit_log row.

## Phase 5.4 — trade journal assistant (untested)

- [ ] **Sidebar has "Journal"** link between Signals and Settings.
- [ ] `/journal` page: scope dropdowns (account, strategy), lookback days input,
      preset prompt chips, big Ask button.
- [ ] Empty scope → Ask refuses with a clear error.
- [ ] Asking "summarise my last week of trading" with an account scoped returns a useful
      markdown answer in &lt;15s.
- [ ] `/ai/calls` shows a row with `purpose=journal_ask` and sensible cost (~$0.01-0.05).
- [ ] Scope leakage check: as a non-admin, querying with another user's account_id returns 403,
      not data.

## Phase 5.3 — opportunity scanner (untested)

- [ ] Migration `0007_signals` runs cleanly.
- [ ] Worker logs show `scanner.persisted count=N` (or `scanner.skipped reason=...`) at
      :03 and :33 past every hour after the next deploy.
- [ ] `/signals` page populates with cards after the first run (~30 min wait).
- [ ] Each card shows: symbol, direction pill, rationale, score bar, confidence %, horizon.
- [ ] `/ai/calls` shows rows with purpose=`scan_opportunities` and a sensible cost (typically
      $0.01–0.05 per call on Sonnet).
- [ ] Manually trigger a scan instead of waiting:
      ```
      docker compose exec -T worker python - <<PY
      import asyncio
      from arq import create_pool
      from arq.connections import RedisSettings
      import os

      async def go():
          pool = await create_pool(RedisSettings.from_dsn(os.environ['REDIS_URL']))
          await pool.enqueue_job('scan_opportunities')
          print('enqueued')
          await pool.close()

      asyncio.run(go())
      PY
      ```
- [ ] If the model returns malformed JSON, `scanner.parse_failed` logs the preview and the
      task completes with zero signals (not a crash).
- [ ] Signals expire after 6 hours (`expires_at` column populated, list endpoint filters them).

## Phase 5.2 — strategy optimizer (untested)

- [ ] **Optimize with AI** button on `/backtests/[id]` (only visible when status=done).
- [ ] Dialog shows the rationale + proposed code from the model in clearly separated panes.
- [ ] **Apply as new version** creates a new `strategy_versions` row with message
      `"AI optimize (<provider> <model>)"` and navigates back to the editor.
- [ ] `/ai/calls` row appears with purpose=`strategy_optimize`.
- [ ] If the model omits the `=== CODE ===` separator, the rationale is empty and the entire
      response lands in the code pane (degraded but still usable).

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
- [ ] **After every deploy, smoke-test the master key path.** A fresh symptom we hit: secret
      mounted but unreadable by the non-root container user manifested only on the first
      encryption attempt. Always confirm with:
      `docker compose exec api cat /run/secrets/master_key | wc -c`  → should print `32`.
- [ ] Kill switch script (`infra/scripts/kill-switch.sh`) stops workers cleanly. Try it once on the
      VPS so you've used it before the day you need to.
- [ ] Outage drill: stop postgres for 30s, then start it. API + worker should reconnect cleanly,
      live strategies recover from the next bar.
