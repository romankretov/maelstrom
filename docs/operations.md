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
