#!/usr/bin/env bash
# bootstrap.sh — provision a fresh Ubuntu 24.04 VPS for Maelstrom.
#
# Run as root on a fresh VPS:
#   curl -fsSL https://raw.githubusercontent.com/romankretov/maelstrom/main/infra/bootstrap.sh | sudo bash -s -- \
#       --ssh-key "ssh-ed25519 AAAA... your@laptop" \
#       --repo  romankretov/maelstrom \
#       --domain maelstromhub.com
#
# Idempotent: safe to re-run. Each step checks if it's already done.

set -euo pipefail

SSH_PUBKEY=""
REPO_SLUG=""
DOMAIN=""
DEPLOY_USER="deploy"
APP_DIR="/opt/maelstrom"
SECRETS_DIR="/etc/maelstrom"
SWAP_SIZE_MB=4096

while [[ $# -gt 0 ]]; do
    case "$1" in
        --ssh-key)   SSH_PUBKEY="$2"; shift 2 ;;
        --repo)      REPO_SLUG="$2"; shift 2 ;;
        --domain)    DOMAIN="$2"; shift 2 ;;
        --user)      DEPLOY_USER="$2"; shift 2 ;;
        --app-dir)   APP_DIR="$2"; shift 2 ;;
        --swap-mb)   SWAP_SIZE_MB="$2"; shift 2 ;;
        -h|--help)
            grep '^#' "$0" | sed 's/^# \{0,1\}//'
            exit 0
            ;;
        *) echo "Unknown arg: $1" >&2; exit 1 ;;
    esac
done

require() { [[ -n "${!1:-}" ]] || { echo "Missing --${1//_/-}" >&2; exit 1; }; }
require SSH_PUBKEY
require REPO_SLUG
require DOMAIN

if [[ "$(id -u)" -ne 0 ]]; then
    echo "Must run as root" >&2; exit 1
fi

step() { printf '\n\033[1;34m==>\033[0m %s\n' "$*"; }

# ---------------------------------------------------------------------------
step "APT update + base packages"
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get -y upgrade
apt-get -y install \
    ca-certificates curl gnupg lsb-release \
    git ufw fail2ban unattended-upgrades htop ncdu jq \
    apt-transport-https rsync

# ---------------------------------------------------------------------------
step "Create deploy user (${DEPLOY_USER})"
if ! id -u "${DEPLOY_USER}" >/dev/null 2>&1; then
    useradd -m -s /bin/bash -G sudo "${DEPLOY_USER}"
    echo "${DEPLOY_USER} ALL=(ALL) NOPASSWD: /usr/bin/docker, /usr/local/bin/docker-compose, /usr/bin/systemctl" \
        > "/etc/sudoers.d/90-${DEPLOY_USER}"
    chmod 0440 "/etc/sudoers.d/90-${DEPLOY_USER}"
fi
install -d -m 0700 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "/home/${DEPLOY_USER}/.ssh"
AUTHFILE="/home/${DEPLOY_USER}/.ssh/authorized_keys"
touch "${AUTHFILE}" && chown "${DEPLOY_USER}:${DEPLOY_USER}" "${AUTHFILE}" && chmod 0600 "${AUTHFILE}"
grep -qxF "${SSH_PUBKEY}" "${AUTHFILE}" || echo "${SSH_PUBKEY}" >> "${AUTHFILE}"

# ---------------------------------------------------------------------------
step "SSH hardening"
sshd_conf="/etc/ssh/sshd_config.d/99-maelstrom.conf"
cat > "${sshd_conf}" <<EOF
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
ChallengeResponseAuthentication no
PubkeyAuthentication yes
MaxAuthTries 3
LoginGraceTime 30
AllowUsers ${DEPLOY_USER}
EOF
sshd -t && systemctl reload ssh || systemctl reload sshd

# ---------------------------------------------------------------------------
step "UFW firewall"
ufw default deny incoming
ufw default allow outgoing
ufw allow 22/tcp
ufw allow 80/tcp
ufw allow 443/tcp
ufw allow 443/udp  # HTTP/3
ufw --force enable

# ---------------------------------------------------------------------------
step "Fail2ban"
cat > /etc/fail2ban/jail.d/sshd.conf <<'EOF'
[sshd]
enabled = true
port = ssh
maxretry = 4
bantime = 1h
findtime = 10m
EOF
systemctl enable --now fail2ban
systemctl restart fail2ban

# ---------------------------------------------------------------------------
step "Unattended security upgrades"
cat > /etc/apt/apt.conf.d/52unattended-upgrades-local <<'EOF'
Unattended-Upgrade::Automatic-Reboot "false";
Unattended-Upgrade::Remove-Unused-Dependencies "true";
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
EOF
systemctl enable --now unattended-upgrades

# ---------------------------------------------------------------------------
step "Swap (${SWAP_SIZE_MB} MB)"
if [[ ! -f /swapfile ]]; then
    fallocate -l "${SWAP_SIZE_MB}M" /swapfile
    chmod 600 /swapfile
    mkswap /swapfile
    swapon /swapfile
    grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi
sysctl -w vm.swappiness=10
grep -q '^vm.swappiness' /etc/sysctl.conf || echo 'vm.swappiness=10' >> /etc/sysctl.conf

# ---------------------------------------------------------------------------
step "Docker engine + Compose plugin"
if ! command -v docker >/dev/null 2>&1; then
    install -m 0755 -d /etc/apt/keyrings
    curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
        | gpg --dearmor -o /etc/apt/keyrings/docker.gpg
    chmod a+r /etc/apt/keyrings/docker.gpg
    echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.gpg] \
        https://download.docker.com/linux/ubuntu $(lsb_release -cs) stable" \
        > /etc/apt/sources.list.d/docker.list
    apt-get update
    apt-get -y install docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
usermod -aG docker "${DEPLOY_USER}"
systemctl enable --now docker

# Docker daemon limits for log files (belt-and-braces; compose also sets them)
mkdir -p /etc/docker
if [[ ! -f /etc/docker/daemon.json ]]; then
    cat > /etc/docker/daemon.json <<'EOF'
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "5" },
  "live-restore": true
}
EOF
    systemctl restart docker || true
fi

# ---------------------------------------------------------------------------
step "Secrets directory + master key"
install -d -m 0700 -o root -g root "${SECRETS_DIR}"
MASTER_KEY="${SECRETS_DIR}/master.key"
if [[ ! -f "${MASTER_KEY}" ]]; then
    head -c 32 /dev/urandom > "${MASTER_KEY}"
    chown root:root "${MASTER_KEY}"
    chmod 0400 "${MASTER_KEY}"
    echo "Generated ${MASTER_KEY}. BACK THIS UP somewhere safe — losing it loses all encrypted API keys."
fi

# ---------------------------------------------------------------------------
step "Clone repo to ${APP_DIR}"
install -d -m 0755 -o "${DEPLOY_USER}" -g "${DEPLOY_USER}" "${APP_DIR}"
if [[ ! -d "${APP_DIR}/.git" ]]; then
    sudo -u "${DEPLOY_USER}" git clone "https://github.com/${REPO_SLUG}.git" "${APP_DIR}"
else
    sudo -u "${DEPLOY_USER}" git -C "${APP_DIR}" pull --ff-only origin main
fi

# ---------------------------------------------------------------------------
step "Seed .env if missing"
ENVFILE="${APP_DIR}/.env"
if [[ ! -f "${ENVFILE}" ]]; then
    cp "${APP_DIR}/.env.example" "${ENVFILE}"
    sed -i "s|^MAELSTROM_DOMAIN=.*|MAELSTROM_DOMAIN=${DOMAIN}|" "${ENVFILE}"
    sed -i "s|^MAELSTROM_ENV=.*|MAELSTROM_ENV=production|" "${ENVFILE}"
    sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=$(openssl rand -base64 24 | tr -d '=+/')|" "${ENVFILE}"
    sed -i "s|^API_SECRET_KEY=.*|API_SECRET_KEY=$(openssl rand -base64 48 | tr -d '=+/' | head -c 64)|" "${ENVFILE}"
    sed -i "s|^NEXT_PUBLIC_API_BASE_URL=.*|NEXT_PUBLIC_API_BASE_URL=https://${DOMAIN}/api|" "${ENVFILE}"
    sed -i "s|^NEXT_PUBLIC_WS_BASE_URL=.*|NEXT_PUBLIC_WS_BASE_URL=wss://${DOMAIN}/ws|" "${ENVFILE}"
    chown "${DEPLOY_USER}:${DEPLOY_USER}" "${ENVFILE}"
    chmod 0600 "${ENVFILE}"
    echo "Wrote ${ENVFILE} with generated passwords. Review before first deploy."
fi

# ---------------------------------------------------------------------------
step "Done"
cat <<EOF

✅  VPS bootstrap complete.

Next steps (run on your laptop):
  1. Add these GitHub Actions secrets at
     https://github.com/${REPO_SLUG}/settings/secrets/actions
       - DEPLOY_HOST   = <this VPS IP or ${DOMAIN}>
       - DEPLOY_USER   = ${DEPLOY_USER}
       - DEPLOY_SSH_KEY = <private key matching the public one you registered>

  2. Push a commit to main and click "Deploy" in Actions.

To trigger a deploy from this VPS for the first time:
       cd ${APP_DIR}
       sudo -u ${DEPLOY_USER} docker compose -f compose.prod.yml --profile tools run --rm migrate
       sudo -u ${DEPLOY_USER} docker compose -f compose.prod.yml up -d

To create your admin user once it's running:
       curl -X POST https://${DOMAIN}/api/auth/register \\
            -H 'Content-Type: application/json' \\
            -d '{"email":"you@example.com","password":"<strong-password>"}'
  Then update the role in the DB:
       sudo -u ${DEPLOY_USER} docker compose -f compose.prod.yml exec postgres \\
            psql -U \$POSTGRES_USER -d \$POSTGRES_DB -c \\
            "UPDATE users SET role='admin', is_superuser=true WHERE email='you@example.com';"

EOF
