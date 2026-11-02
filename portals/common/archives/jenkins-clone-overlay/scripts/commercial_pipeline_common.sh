#!/usr/bin/env bash
# Shared helpers for commercial platform pipelines.
set -euo pipefail

SCRIPT_DIR_COMMON="$(cd "$(dirname "${BASH_SOURCE[0]:-$0}")" && pwd)"
# shellcheck disable=SC1091
. "$SCRIPT_DIR_COMMON/jenkins_build_step_push.sh"

_pipeline_notify_build_complete() {
  local result="${1:-SUCCESS}"
  local instance_id="${JENKINS_INSTANCE_ID:-}"
  local build_number="${BUILD_NUMBER:-}"
  if [[ -z "$instance_id" || -z "$build_number" ]]; then
    echo "[webhook] skip build-complete (missing instance/build)"
    return 0
  fi
  if [[ "$result" == "ABORTED" ]]; then
    _pipeline_push_build_step "END" "stopped" "流水线结束" "构建已停止"
  elif [[ "$result" == "FAILURE" || "$result" == "UNSTABLE" ]]; then
    _pipeline_push_build_step "END" "failed" "流水线结束" "构建失败"
  else
    _pipeline_push_build_step "END" "success" "流水线结束" "构建完成"
  fi
  local payload
  payload=$(printf '{"instance_id":"%s","build_number":"%s","result":"%s","platform":"%s","job":"%s"}' \
    "$(_pipeline_json_escape "$instance_id")" \
    "$build_number" \
    "$(_pipeline_json_escape "$result")" \
    "$(_pipeline_json_escape "${RELEASE_PLATFORM:-}")" \
    "$(_pipeline_json_escape "${JOB_NAME:-}")")
  _pipeline_post_webhook "/api/internal/jenkins/build-complete" "$payload"
}

_pipeline_resolve_python() {
  if command -v py >/dev/null 2>&1; then echo "py -3"; return; fi
  if command -v python3 >/dev/null 2>&1; then echo "python3"; return; fi
  if command -v python >/dev/null 2>&1; then echo "python"; return; fi
  echo ""
}
