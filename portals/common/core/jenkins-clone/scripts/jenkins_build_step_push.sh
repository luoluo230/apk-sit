#!/usr/bin/env bash
# Jenkins → Portal packaging step push (Android / iOS). Safe to source; no set -e.
# Requires: APKSITE_BASE_URL, JENKINS_INSTANCE_ID, BUILD_NUMBER
# Optional: JENKINS_BUILD_WEBHOOK_SECRET, WEBHOOK_AUTH_DISABLED=1 (dev)

_pipeline_json_escape() {
  printf '%s' "${1:-}" | sed -e 's/\\/\\\\/g' -e 's/"/\\"/g' -e ':a;N;$!ba;s/\n/\\n/g'
}

_pipeline_post_webhook() {
  local path="$1"
  local payload="$2"
  local portal="${APKSITE_BASE_URL:-http://127.0.0.1:5003}"
  local secret="${JENKINS_BUILD_WEBHOOK_SECRET:-}"
  local auth_disabled="${WEBHOOK_AUTH_DISABLED:-}"
  local -a headers
  headers=(-H "Content-Type: application/json")
  if [ -n "$secret" ]; then
    local sig
    sig=$(printf '%s' "$payload" | openssl dgst -sha256 -hmac "$secret" 2>/dev/null | awk '{print $2}')
    if [ -z "$sig" ]; then
      echo "[webhook] skip ${path} (openssl unavailable)"
      return 0
    fi
    headers+=(-H "X-Jenkins-Signature: sha256=${sig}")
  elif [ "${auth_disabled}" != "1" ] && [ "${auth_disabled}" != "true" ]; then
    echo "[webhook] skip ${path} (missing JENKINS_BUILD_WEBHOOK_SECRET)"
    return 0
  fi
  if command -v curl >/dev/null 2>&1; then
    curl -sf -X POST "${portal%/}${path}" "${headers[@]}" -d "$payload" >/dev/null \
      && echo "[webhook] ${path} OK" \
      || echo "[webhook] ${path} failed"
  else
    echo "[webhook] skip ${path} (curl unavailable)"
  fi
}

_pipeline_push_build_step() {
  # Usage: _pipeline_push_build_step <stage_key> <status> <label> [detail]
  local stage_key="${1:-}"
  local status="${2:-running}"
  local label="${3:-}"
  local detail="${4:-}"
  local instance_id="${JENKINS_INSTANCE_ID:-}"
  local build_number="${BUILD_NUMBER:-}"
  if [ -z "$instance_id" ] || [ -z "$build_number" ]; then
    echo "[webhook] skip build-step (missing instance/build) stage=${stage_key} status=${status}"
    return 0
  fi
  local platform
  platform=$(printf '%s' "${RELEASE_PLATFORM:-android}" | tr '[:upper:]' '[:lower:]')
  local payload
  payload=$(printf '{"instance_id":"%s","build_number":%s,"stage_key":"%s","status":"%s","label":"%s","detail":"%s","platform":"%s","job":"%s"}' \
    "$(_pipeline_json_escape "$instance_id")" \
    "$build_number" \
    "$(_pipeline_json_escape "$stage_key")" \
    "$(_pipeline_json_escape "$status")" \
    "$(_pipeline_json_escape "$label")" \
    "$(_pipeline_json_escape "$detail")" \
    "$(_pipeline_json_escape "$platform")" \
    "$(_pipeline_json_escape "${JOB_NAME:-}")")
  _pipeline_post_webhook "/api/internal/jenkins/build-step" "$payload"
}
