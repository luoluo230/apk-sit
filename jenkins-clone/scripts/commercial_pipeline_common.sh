#!/usr/bin/env bash
# Shared helpers for commercial platform pipelines.
set -euo pipefail

_pipeline_notify_build_complete() {
  local result="${1:-SUCCESS}"
  local portal="${APKSITE_BASE_URL:-http://127.0.0.1:5003}"
  local secret="${JENKINS_BUILD_WEBHOOK_SECRET:-}"
  local instance_id="${JENKINS_INSTANCE_ID:-}"
  local build_number="${BUILD_NUMBER:-}"
  if [[ -z "$secret" || -z "$instance_id" || -z "$build_number" ]]; then
    echo "[webhook] skip build-complete (missing secret/instance/build)"
    return 0
  fi
  local payload ts to_sign digest sig_header
  payload=$(printf '{"instance_id":"%s","build_number":"%s","result":"%s","platform":"%s","job":"%s"}' \
    "$instance_id" "$build_number" "$result" "${RELEASE_PLATFORM:-}" "${JOB_NAME:-}")
  ts=$(date +%s)
  to_sign="${ts}.${payload}"
  digest=$(printf '%s' "$to_sign" | openssl dgst -sha256 -hmac "$secret" 2>/dev/null | awk '{print $2}')
  if [[ -n "$digest" ]]; then
    sig_header="t=${ts},v1=${digest}"
    curl -sf -X POST "${portal%/}/api/internal/jenkins/build-complete" \
      -H "Content-Type: application/json" \
      -H "X-Signature-SHA256: ${sig_header}" \
      -d "$payload" >/dev/null && echo "[webhook] build-complete OK" || echo "[webhook] build-complete failed"
    return 0
  fi
  local sig
  sig=$(printf '%s' "$payload" | openssl dgst -sha256 -hmac "$secret" 2>/dev/null | awk '{print $2}')
  if [[ -z "$sig" ]]; then
    echo "[webhook] skip (openssl unavailable)"
    return 0
  fi
  curl -sf -X POST "${portal%/}/api/internal/jenkins/build-complete" \
    -H "Content-Type: application/json" \
    -H "X-Jenkins-Signature: sha256=${sig}" \
    -d "$payload" >/dev/null && echo "[webhook] build-complete OK (legacy sig)" || echo "[webhook] build-complete failed"
}

_pipeline_resolve_python() {
  if command -v py >/dev/null 2>&1; then echo "py -3"; return; fi
  if command -v python3 >/dev/null 2>&1; then echo "python3"; return; fi
  if command -v python >/dev/null 2>&1; then echo "python"; return; fi
  echo ""
}
