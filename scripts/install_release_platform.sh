#!/usr/bin/env bash
# Install release platform build node (macOS iOS).
set -euo pipefail

ROLE="build-ios"
JENKINS_MASTER_URL="http://127.0.0.1:8082"
PORTAL_BASE_URL="http://127.0.0.1:5003"
UNITY_VERSION=""
NODE_ID=""
APK_SITE_ROOT=""
SKIP_AGENT=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --role) ROLE="$2"; shift 2 ;;
    --jenkins-master-url) JENKINS_MASTER_URL="$2"; shift 2 ;;
    --portal-base-url) PORTAL_BASE_URL="$2"; shift 2 ;;
    --unity-version) UNITY_VERSION="$2"; shift 2 ;;
    --node-id) NODE_ID="$2"; shift 2 ;;
    --apk-site-root) APK_SITE_ROOT="$2"; shift 2 ;;
    --skip-agent) SKIP_AGENT=1; shift ;;
    *) echo "Unknown arg: $1"; exit 1 ;;
  esac
done

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
if [[ -z "$APK_SITE_ROOT" ]]; then
  APK_SITE_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

log() { echo "[install] $*"; }

send_heartbeat() {
  local secret="${BUILD_NODE_WEBHOOK_SECRET:-${JENKINS_BUILD_WEBHOOK_SECRET:-}}"
  if [[ -z "$secret" ]]; then
    echo "[install] skip heartbeat (secret not set)"
    return 0
  fi
  local nid="${NODE_ID:-build-ios-$(hostname -s)}"
  local payload
  payload=$(cat <<EOF
{"role":"build-ios","node_id":"${nid}","hostname":"$(hostname -s)","agent_name":"$(hostname -s)","os":"darwin","jenkins_master_url":"${JENKINS_MASTER_URL}","unity_version":"${UNITY_VERSION}"}
EOF
)
  local sig
  sig=$(printf '%s' "$payload" | openssl dgst -sha256 -hmac "$secret" | awk '{print $2}')
  curl -sf -X POST "${PORTAL_BASE_URL}/api/internal/build-nodes/heartbeat" \
    -H "Content-Type: application/json" \
    -H "X-Build-Node-Signature: sha256=${sig}" \
    -d "$payload" >/dev/null || echo "[install] heartbeat failed"
}

log "install_release_platform role=$ROLE"

if ! command -v xcodebuild >/dev/null 2>&1; then
  echo "[install] WARN: xcodebuild not found. Install Xcode Command Line Tools."
fi

if [[ "$SKIP_AGENT" -eq 0 ]]; then
  bash "$SCRIPT_DIR/jenkins_agent_bootstrap.sh" --role build-ios --jenkins-master-url "$JENKINS_MASTER_URL" --node-name "ios-$(hostname -s)" || true
fi

send_heartbeat
echo "=== install_release_platform DONE ($ROLE) ==="
