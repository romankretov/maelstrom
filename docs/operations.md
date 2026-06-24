# Operations runbook

## First-time VPS setup

1. Buy Hostinger KVM 4 (or larger), Ubuntu 24.04 image, note the IP.
2. In Hostinger DNS for `maelstromhub.com`:
   - `A @` → VPS IP
   - `A www` → VPS IP
3. SSH in as root and run `infra/bootstrap.sh` (see README).
4. Add GitHub Actions secrets (see README).
5. Trigger first deploy.

## Routine deploys

`make deploy TAG=<sha-or-main>` from your laptop, or click "Run workflow" on the
**Deploy** action in GitHub.

The workflow:
1. SSHes in as `deploy@maelstromhub.com`
2. Pulls images for the requested tag
3. Runs `alembic upgrade head`
4. `docker compose up -d --remove-orphans`
5. Calls `healthcheck.sh`; on failure runs `rollback.sh`

## Adding a Hyperliquid account end-to-end

End goal: a strategy you wrote runs live on Hyperliquid (testnet first,
mainnet only after you've smoke-tested).

1. **Generate an agent wallet on Hyperliquid testnet.** Go to
   https://app.hyperliquid-testnet.xyz → settings → API → "Generate an
   agent wallet". The agent has trading rights only — it can't withdraw
   funds. Copy its **wallet address** and **private key**.
2. Fund the master wallet with testnet USDC from the faucet on the same
   page. Approve the agent (one-time).
3. **In Maelstrom UI** → `/portfolio` → **+ New account** → pick
   **Hyperliquid testnet** → name it (e.g. `hl-testnet`), set a
   reference starting capital (just for return-% math) → Create. The
   new account auto-selects.
4. The Credentials card appears below the account picker. Click **Add
   credentials** → paste wallet address + private key → Save. The key
   is encrypted with the VPS master key (libsodium SecretBox) before it
   hits Postgres. It is never returned by any API and never written to
   `audit_log` payloads.
5. Go to `/strategies` → open a strategy → click **Run live**. Pick the
   `hl-testnet` account. Set **Max notional per symbol** as a safety
   belt — `100` is sensible while you're sanity-checking.
6. The Live runs card on the strategy page shows the new row flipping
   `pending_start → running` within ~3s. As bars arrive, any
   `self.buy/sell` call routes through `HyperliquidBroker.submit` which
   places a market order on testnet.
7. Watch logs: `docker compose logs -f worker | grep -E 'hl.fill|hl.reject|reconcile'`.
8. Cross-check on Hyperliquid testnet UI that the order + position match
   what `/portfolio` shows.

### Going to mainnet

Only after you've completed steps 1–8 above on testnet.

1. On the VPS, set `MAELSTROM_ALLOW_MAINNET=1` in `/opt/maelstrom/.env`
   and restart api+worker. Without this env var, the API refuses to
   create `live_hl_main` accounts even from admin.
2. Repeat the agent-wallet steps on Hyperliquid mainnet
   (https://app.hyperliquid.xyz).
3. **+ New account** → **Hyperliquid mainnet** → the dialog warns you
   first; confirm. Same credentials flow.
4. **Start tiny.** Set `max_notional_per_symbol = 50` (or less). Confirm
   one round-trip works before scaling up.
5. Stash `/etc/maelstrom/master.key` somewhere durable (1Password).
   Losing it means every encrypted exchange key in the DB becomes
   unrecoverable — including the one funding your mainnet account.

## Emergency

| Situation                  | Action                                                                       |
| -------------------------- | ---------------------------------------------------------------------------- |
| Strategies misbehaving     | `ssh deploy@... && cd /opt/maelstrom && ./infra/scripts/kill-switch.sh`      |
| Bad deploy after healthcheck passed | `ssh deploy@... && cd /opt/maelstrom && ./infra/scripts/rollback.sh` |
| API down but DB fine       | `docker compose -f compose.prod.yml restart api`                             |
| DB unreachable             | Check disk space (`df -h`), then `journalctl -u docker --since "10m ago"`    |
| Lost master.key            | All encrypted exchange keys are unrecoverable. Re-enter via UI after restore.|

## Backup

A `backup` container in `compose.prod.yml` runs `pg_dump` once per
`BACKUP_INTERVAL` (default 24h) and writes gzipped dumps to
`/opt/maelstrom/backups/` on the VPS. Retention is
`BACKUP_RETENTION_DAYS` (default 14).

For offsite copies, set `RCLONE_REMOTE_PATH` (e.g. `b2:bucket/maelstrom`)
and `RCLONE_CONFIG_BASE64` in `.env`. See `.env.example` for the rclone
setup.

To **manually dump right now** without waiting for the next cycle:
```bash
ssh deploy@maelstromhub.com
cd /opt/maelstrom
docker compose -f compose.prod.yml exec -T postgres \
  pg_dump -U "$(grep ^POSTGRES_USER .env | cut -d= -f2)" \
          -d "$(grep ^POSTGRES_DB .env | cut -d= -f2)" \
  | gzip > "/opt/maelstrom/backups/manual-$(date -u +%FT%H%MZ).sql.gz"
```

To **restore from a backup** (DESTRUCTIVE — drops + recreates public
schema, then re-runs the dump):
```bash
ssh deploy@maelstromhub.com
cd /opt/maelstrom
./infra/scripts/restore.sh                          # newest backup
./infra/scripts/restore.sh maelstrom-2026...sql.gz  # specific file
```
The script will prompt you to type the filename to confirm.

### The master key

`/etc/maelstrom/master.key` encrypts everything in `accounts.api_key_enc`,
`llm_providers.api_key_enc`, and `notification_channels.secret_enc`. If
you lose it, ALL of those become unrecoverable — even with a fresh DB
restore.

Stash a copy off-VPS the moment you bootstrap:
```bash
sudo base64 < /etc/maelstrom/master.key
# paste into 1Password / similar
```

To **restore the master key on a new VPS**, write the decoded bytes back
to `/etc/maelstrom/master.key`, then `chmod 0444` it.
