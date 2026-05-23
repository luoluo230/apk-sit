#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

APP_USER="${APP_USER:-www-data}"
APP_GROUP="${APP_GROUP:-$APP_USER}"
APP_NAME="${APP_NAME:-apk-site}"
APP_PORT="${APP_PORT:-5003}"
PUBLIC_HOST="${PUBLIC_HOST:-}"
PUBLIC_URL="${PUBLIC_URL:-}"
APK_DIR_INPUT="${APK_DIR:-$APP_DIR/data/apk}"
ENABLE_NGINX="${ENABLE_NGINX:-1}"
ENABLE_UFW="${ENABLE_UFW:-0}"
INSTALL_JENKINS_DEPS="${INSTALL_JENKINS_DEPS:-0}"
ENABLE_HTTPS="${ENABLE_HTTPS:-0}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage:
  sudo bash scripts/cloud_deploy.sh

Common overrides:
  APP_USER=ubuntu
  APP_PORT=5003
  APK_DIR=/data/apks
  PUBLIC_HOST=apk.example.com
  PUBLIC_URL=https://apk.example.com
  ENABLE_NGINX=1
  ENABLE_UFW=0
  INSTALL_JENKINS_DEPS=0
  ENABLE_HTTPS=0
  CERTBOT_EMAIL=ops@example.com
EOF
    exit 0
fi

if [[ "$EUID" -ne 0 ]]; then
    echo "[ERROR] Run this script with sudo or as root."
    exit 1
fi

if [[ "$(uname -s)" != "Linux" ]]; then
    echo "[ERROR] This script supports Linux cloud servers only."
    exit 1
fi

if [[ -f /etc/os-release ]]; then
    . /etc/os-release
    if [[ "${ID:-}" != "ubuntu" && "${ID:-}" != "debian" ]]; then
        echo "[ERROR] Unsupported OS: ${PRETTY_NAME:-unknown}. Use Ubuntu or Debian."
        exit 1
    fi
fi

log() {
    echo "[INFO] $*"
}

apt_install() {
    DEBIAN_FRONTEND=noninteractive apt-get install -y "$@"
}

ensure_user() {
    if ! id -u "$APP_USER" >/dev/null 2>&1; then
        log "Creating user $APP_USER"
        useradd --system --create-home --shell /bin/bash "$APP_USER"
    fi
    getent group "$APP_GROUP" >/dev/null 2>&1 || groupadd --system "$APP_GROUP"
    usermod -a -G "$APP_GROUP" "$APP_USER" >/dev/null 2>&1 || true
}

ensure_env() {
    local env_file="$APP_DIR/.env"
    if [[ ! -f "$env_file" && -f "$APP_DIR/.env.example" ]]; then
        cp "$APP_DIR/.env.example" "$env_file"
    fi
    touch "$env_file"

    python3 - "$env_file" "$APK_DIR_INPUT" "$APP_PORT" "$PUBLIC_URL" "$PUBLIC_HOST" <<'PY'
import sys
from pathlib import Path

env_path = Path(sys.argv[1])
apk_dir = sys.argv[2]
app_port = sys.argv[3]
public_url = sys.argv[4]
public_host = sys.argv[5]

updates = {
    "APK_DIR": apk_dir,
    "APK_PORT": app_port,
    "APK_HOST": "0.0.0.0",
    "APK_DEBUG": "false",
}
if public_url:
    updates["PUBLIC_URL"] = public_url
if public_host and not public_url:
    updates["EXTERNAL_DOMAIN"] = public_host

lines = env_path.read_text(encoding="utf-8", errors="ignore").splitlines() if env_path.exists() else []
seen = set()
out = []
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in updates:
            out.append(f"{key}={updates[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in updates.items():
    if key not in seen:
        out.append(f"{key}={value}")
env_path.write_text("\n".join(out).rstrip() + "\n", encoding="utf-8")
PY
}

install_packages() {
    log "Installing system packages"
    apt-get update
    apt_install python3 python3-venv python3-pip nginx curl git build-essential libssl-dev libffi-dev
    if [[ "$ENABLE_HTTPS" == "1" ]]; then
        apt_install certbot python3-certbot-nginx
    fi
    if [[ "$INSTALL_JENKINS_DEPS" == "1" ]]; then
        apt_install openjdk-17-jre-headless
    fi
}

install_python_deps() {
    log "Creating virtual environment"
    if [[ ! -d "$APP_DIR/venv" ]]; then
        python3 -m venv "$APP_DIR/venv"
    fi

    log "Installing Python dependencies"
    "$APP_DIR/venv/bin/python" -m pip install --upgrade pip
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt"
    if [[ -f "$APP_DIR/requirements-prod.txt" ]]; then
        "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements-prod.txt"
    else
        "$APP_DIR/venv/bin/pip" install gunicorn
    fi
}

prepare_dirs() {
    log "Preparing directories"
    mkdir -p "$APP_DIR/logs" "$APP_DIR/data" "$APK_DIR_INPUT"
    chown -R "$APP_USER:$APP_GROUP" "$APP_DIR"
}

write_service() {
    log "Writing systemd service"
    cat > "/etc/systemd/system/${APP_NAME}.service" <<EOF
[Unit]
Description=APK Site Service
After=network.target

[Service]
Type=simple
User=${APP_USER}
Group=${APP_GROUP}
WorkingDirectory=${APP_DIR}
Environment=PYTHONUNBUFFERED=1
ExecStart=${APP_DIR}/venv/bin/gunicorn -c ${APP_DIR}/gunicorn_config.py app_new:app --bind 127.0.0.1:${APP_PORT}
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

    systemctl daemon-reload
    systemctl enable "${APP_NAME}.service"
    systemctl restart "${APP_NAME}.service"
}

write_nginx() {
    if [[ "$ENABLE_NGINX" != "1" ]]; then
        return
    fi

    local server_name="${PUBLIC_HOST:-_}"
    log "Writing nginx config for ${server_name}"
    cat > "/etc/nginx/sites-available/${APP_NAME}" <<EOF
server {
    listen 80;
    server_name ${server_name};

    client_max_body_size 200m;

    location / {
        proxy_pass http://127.0.0.1:${APP_PORT};
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_read_timeout 300;
    }
}
EOF

    ln -sf "/etc/nginx/sites-available/${APP_NAME}" "/etc/nginx/sites-enabled/${APP_NAME}"
    rm -f /etc/nginx/sites-enabled/default
    nginx -t
    systemctl enable nginx
    systemctl restart nginx
}

configure_ufw() {
    if [[ "$ENABLE_UFW" != "1" ]]; then
        return
    fi
    if command -v ufw >/dev/null 2>&1; then
        log "Configuring ufw"
        ufw allow OpenSSH
        ufw allow 'Nginx Full'
        ufw --force enable
    fi
}

configure_https() {
    if [[ "$ENABLE_HTTPS" != "1" ]]; then
        return
    fi
    if [[ -z "$PUBLIC_HOST" || -z "$CERTBOT_EMAIL" ]]; then
        echo "[ERROR] ENABLE_HTTPS=1 requires PUBLIC_HOST and CERTBOT_EMAIL."
        exit 1
    fi

    log "Requesting Let's Encrypt certificate for ${PUBLIC_HOST}"
    certbot --nginx \
        --non-interactive \
        --agree-tos \
        -m "$CERTBOT_EMAIL" \
        -d "$PUBLIC_HOST" \
        --redirect
}

verify() {
    log "Verifying service"
    systemctl --no-pager --full status "${APP_NAME}.service" || true
    sleep 2
    curl -fsS "http://127.0.0.1:${APP_PORT}/health"
}

main() {
    ensure_user
    ensure_env
    install_packages
    install_python_deps
    prepare_dirs
    write_service
    write_nginx
    configure_ufw
    configure_https
    verify

    cat <<EOF

[DONE] Cloud deployment finished.
App dir:     ${APP_DIR}
Service:     ${APP_NAME}.service
Port:        ${APP_PORT}
APK dir:     ${APK_DIR_INPUT}
Public host: ${PUBLIC_HOST:-not configured}

Useful commands:
  systemctl status ${APP_NAME}.service
  journalctl -u ${APP_NAME}.service -f
  systemctl restart ${APP_NAME}.service
EOF
}

main "$@"
