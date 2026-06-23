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

Phase 7 wires automated backups. Until then, manual:

```bash
ssh deploy@maelstromhub.com
docker compose -f /opt/maelstrom/compose.prod.yml exec -T postgres \
  pg_dump -U $POSTGRES_USER -d $POSTGRES_DB | gzip > /tmp/maelstrom-$(date +%F).sql.gz
sudo cp /etc/maelstrom/master.key /tmp/master.key
# Then scp both files somewhere safe.
```
