#!/usr/bin/env bash
set -euo pipefail

PUBLIC_HOST="${PUBLIC_HOST:-}"
CERTBOT_EMAIL="${CERTBOT_EMAIL:-}"
APP_NAME="${APP_NAME:-apk-site}"

if [[ "${1:-}" == "--help" || "${1:-}" == "-h" ]]; then
    cat <<'EOF'
Usage:
  sudo PUBLIC_HOST=apk.example.com CERTBOT_EMAIL=ops@example.com bash scripts/setup_https.sh
EOF
    exit 0
fi

if [[ "$EUID" -ne 0 ]]; then
    echo "[ERROR] Run this script with sudo or as root."
    exit 1
fi

if [[ -z "$PUBLIC_HOST" || -z "$CERTBOT_EMAIL" ]]; then
    echo "[ERROR] PUBLIC_HOST and CERTBOT_EMAIL are required."
    exit 1
fi

apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y certbot python3-certbot-nginx
nginx -t
systemctl restart nginx

certbot --nginx \
    --non-interactive \
    --agree-tos \
    -m "$CERTBOT_EMAIL" \
    -d "$PUBLIC_HOST" \
    --redirect

echo "[DONE] HTTPS is enabled for ${PUBLIC_HOST}"
