#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

SSH_HOST="${SSH_HOST:-}"
SSH_USER="${SSH_USER:-root}"
SSH_PORT="${SSH_PORT:-22}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/opt/apk-site}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
PUBLIC_URL="${PUBLIC_URL:-}"
APP_USER="${APP_USER:-www-data}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
APP_PORT="${APP_PORT:-5003}"
APK_DIR="${APK_DIR:-$REMOTE_APP_DIR/data/apk}"
ENABLE_NGINX="${ENABLE_NGINX:-1}"
ENABLE_UFW="${ENABLE_UFW:-0}"
ENABLE_HTTPS="${ENABLE_HTTPS:-0}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
INSTALL_JENKINS_DEPS="${INSTALL_JENKINS_DEPS:-0}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage:
  SSH_HOST=1.2.3.4 SSH_USER=root bash scripts/deploy_remote.sh

Common overrides:
  SSH_PORT=22
  REMOTE_APP_DIR=/opt/apk-site
  PUBLIC_HOST=apk.example.com
  PUBLIC_URL=https://apk.example.com
  APP_USER=ubuntu
  APP_PORT=5003
  ENABLE_HTTPS=1
  CERTBOT_EMAIL=ops@example.com
EOF
    exit 0
fi

if [[ -z "$SSH_HOST" ]]; then
    echo "[ERROR] SSH_HOST is required."
    exit 1
fi

log() {
    echo "[INFO] $*"
}

REMOTE="${SSH_USER}@${SSH_HOST}"
SSH_OPTS=(-p "$SSH_PORT" -o StrictHostKeyChecking=accept-new)

if command -v rsync >/dev/null 2>&1; then
    log "Syncing project with rsync"
    rsync -az --delete \
        --exclude '.git' \
        --exclude 'venv' \
        --exclude '__pycache__' \
        --exclude 'logs/*.log' \
        --exclude 'logs/*.pid' \
        -e "ssh -p ${SSH_PORT} -o StrictHostKeyChecking=accept-new" \
        "$APP_DIR/" "${REMOTE}:${REMOTE_APP_DIR}/"
else
    log "rsync not found, using tar + scp"
    TMP_TAR="$(mktemp "/tmp/apk-site.XXXXXX.tar.gz")"
    tar --exclude='.git' --exclude='venv' --exclude='__pycache__' --exclude='logs/*.log' --exclude='logs/*.pid' \
        -C "$APP_DIR" -czf "$TMP_TAR" .
    ssh "${SSH_OPTS[@]}" "$REMOTE" "mkdir -p '$REMOTE_APP_DIR'"
    scp -P "$SSH_PORT" "$TMP_TAR" "${REMOTE}:${REMOTE_APP_DIR}/deploy.tar.gz"
    ssh "${SSH_OPTS[@]}" "$REMOTE" "cd '$REMOTE_APP_DIR' && tar -xzf deploy.tar.gz && rm -f deploy.tar.gz"
    rm -f "$TMP_TAR"
fi

log "Running remote cloud deployment"
ssh "${SSH_OPTS[@]}" "$REMOTE" \
    "cd '$REMOTE_APP_DIR' && sudo APP_USER='$APP_USER' APP_GROUP='$APP_GROUP' APP_PORT='$APP_PORT' APK_DIR='$APK_DIR' PUBLIC_HOST='$PUBLIC_HOST' PUBLIC_URL='$PUBLIC_URL' ENABLE_NGINX='$ENABLE_NGINX' ENABLE_UFW='$ENABLE_UFW' ENABLE_HTTPS='$ENABLE_HTTPS' CERTBOT_EMAIL='$CERTBOT_EMAIL' INSTALL_JENKINS_DEPS='$INSTALL_JENKINS_DEPS' bash scripts/cloud_deploy.sh"

log "Remote deployment finished"
if [[ -n "$PUBLIC_URL" ]]; then
    echo "[DONE] ${PUBLIC_URL}"
elif [[ -n "$PUBLIC_HOST" ]]; then
    if [[ "$ENABLE_HTTPS" == "1" ]]; then
        echo "[DONE] https://${PUBLIC_HOST}"
    else
        echo "[DONE] http://${PUBLIC_HOST}"
    fi
else
    echo "[DONE] Server: ${SSH_HOST}"
fi
