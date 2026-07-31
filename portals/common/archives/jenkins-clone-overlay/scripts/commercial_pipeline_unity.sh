#!/usr/bin/env bash
# Unity CLI helpers shared by iOS / WxMinigame pipelines.
set -euo pipefail

_resolve_python_cmd() {
  if command -v py >/dev/null 2>&1; then echo "py -3"; return; fi
  if command -v python3 >/dev/null 2>&1; then echo "python3"; return; fi
  if command -v python >/dev/null 2>&1; then echo "python"; return; fi
  echo ""
}

_resolve_unity_exe() {
  local ver="${UNITY_VERSION:-6000.3.8f1}"
  local map_file="${UNITY_PATH_MAP_FILE:-${JENKINS_HOME:-}/unity_paths.json}"
  local resolved=""
  local py_cmd
  py_cmd="$(_resolve_python_cmd)"
  if [ -f "$map_file" ] && [ -n "$py_cmd" ]; then
    resolved=$($py_cmd -c "import json,os; m=json.load(open(os.environ['UNITY_PATH_MAP_FILE'],encoding='utf-8')); print((m.get(os.environ.get('UNITY_VERSION','')) or '').strip())" 2>/dev/null || echo "")
  fi
  if [ -n "$resolved" ] && [ -d "$resolved" ] && [ -f "$resolved/Contents/MacOS/Unity" ]; then
    resolved="$resolved/Contents/MacOS/Unity"
  fi
  if [ -z "$resolved" ] || [ ! -f "$resolved" ]; then
    for CAND in \
      "/c/Program Files/Unity/Hub/Editor/${ver}/Editor/Unity.exe" \
      "/Applications/Unity/Hub/Editor/${ver}/Unity.app/Contents/MacOS/Unity"; do
      if [ -f "$CAND" ]; then resolved="$CAND"; break; fi
    done
  fi
  if [ -n "$resolved" ] && [ -f "$resolved" ]; then echo "$resolved"; fi
}

_cache_unity_services_cdn() {
  local url="https://public-cdn.cloud.unity3d.com/config/production"
  local dest="${JENKINS_HOME:-${TMPDIR:-/tmp}}/unity-services-config-production.json"
  curl -fsS --connect-timeout 10 --max-time 90 "$url" -o "$dest" 2>/dev/null || true
}

_run_unity() {
  local METHOD="$1"; shift
  UNITY_PATH="${UNITY_PATH:-$(_resolve_unity_exe)}"
  if [ ! -f "$UNITY_PATH" ]; then echo "Unity path invalid: $UNITY_PATH"; return 1; fi
  local PROJECT_PATH="${UNITY_PROJECT_PATH:-${GIT_WORKSPACE:-}}"
  if [ -z "$PROJECT_PATH" ] || [ ! -d "$PROJECT_PATH/Assets" ]; then
    echo "UNITY_PROJECT_PATH/GIT_WORKSPACE missing"
    return 1
  fi
  local UNITY_TIMEOUT_SEC="${UNITY_CLI_TIMEOUT_SEC:-7200}"
  local ARGS="-batchmode -nographics -disableAssemblyUpdater -quitTimeout ${UNITY_TIMEOUT_SEC} -projectPath \"$PROJECT_PATH\" -executeMethod $METHOD $*"
  echo "Unity: $UNITY_PATH $ARGS"
  _cache_unity_services_cdn
  set +e
  UNITY_LOG="${UNITY_LOG:-$(mktemp)}"
  eval "\"$UNITY_PATH\" $ARGS" 2>&1 | tee "$UNITY_LOG"
  local UNITY_EC=${PIPESTATUS[0]}
  set -e
  return $UNITY_EC
}

UNITY_PATH="${UNITY_PATH:-$(_resolve_unity_exe)}"
