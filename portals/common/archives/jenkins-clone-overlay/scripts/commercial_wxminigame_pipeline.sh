#!/usr/bin/env bash
# WeChat minigame pipeline: Steps 1-3 + WX-WASM-SDK export + OSS + optional miniprogram-ci.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/commercial_pipeline_common.sh"
. "$SCRIPT_DIR/commercial_pipeline_unity.sh"

export APK_BUILD_ENABLED="${APK_BUILD_ENABLED:-false}"
export RELEASE_PLATFORM="${RELEASE_PLATFORM:-WebGL}"
export WXMINIGAME_BUILD_ENABLED="${WXMINIGAME_BUILD_ENABLED:-true}"
export AUTO_UPLOAD_WX="${AUTO_UPLOAD_WX:-false}"

echo "======= WxMinigame Commercial Pipeline ======="
bash "$SCRIPT_DIR/commercial_android_pipeline.sh"

_log_wx() { echo "[wxminigame] $*"; }

if [ "${WXMINIGAME_BUILD_ENABLED:-false}" != "true" ]; then
  _log_wx "minigame export skipped"
  _pipeline_notify_build_complete SUCCESS
  exit 0
fi

if [ -z "${WX_APP_ID:-}" ]; then
  echo "ERROR: WX_APP_ID required (configure in Portal version/group wx_minigame)"
  exit 1
fi

_log_wx "Step 5: WX-WASM-SDK DoExport"
WX_ARGS="-wxAppId \"${WX_APP_ID}\""
WX_ARGS="$WX_ARGS -wxProjectName \"${WX_PROJECT_NAME:-${APP_NAME:-Game}}\""
WX_ARGS="$WX_ARGS -wxCdnBase \"${WX_CDN_BASE:-}\""
WX_ARGS="$WX_ARGS -releaseVersion \"${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}\""
WX_ARGS="$WX_ARGS -releaseEnvironment \"${RELEASE_ENVIRONMENT:-Development}\""
WX_ARGS="$WX_ARGS -releaseChannel \"${RELEASE_CHANNEL:-common}\""

_run_unity WxMinigameExportCli.ExportFromCommandLine $WX_ARGS || exit $?

WX_BUNDLE="${WXGAME_BUNDLE:-}"
if [ -z "$WX_BUNDLE" ] || [ ! -f "$WX_BUNDLE" ]; then
  WX_BUNDLE=$(find "${OUTPUT_BASE_DIR:-.}" -name "wxgame_bundle.zip" -type f 2>/dev/null | head -n 1)
fi
if [ -z "$WX_BUNDLE" ] || [ ! -f "$WX_BUNDLE" ]; then
  echo "ERROR: wxgame bundle not found"
  exit 1
fi
export WXGAME_BUNDLE="$WX_BUNDLE"
_log_wx "Bundle: $WX_BUNDLE"

PY=$(_pipeline_resolve_python)
ARCHIVE="$SCRIPT_DIR/archive_build_artifact.py"
if [ -n "$PY" ] && [ -f "$ARCHIVE" ]; then
  export ARTIFACT_TYPE=wxgame_bundle
  export ARTIFACT_FILE="$WX_BUNDLE"
  $PY "$ARCHIVE" || exit 1
fi

if [ "${AUTO_UPLOAD_WX:-false}" = "true" ]; then
  _log_wx "Step 6: upload to WeChat (miniprogram-ci optional)"
  UP="$SCRIPT_DIR/upload_wxminigame.py"
  if [ -n "$PY" ] && [ -f "$UP" ]; then
    $PY || echo "WARN: WeChat upload failed"
  fi
fi

_pipeline_notify_build_complete SUCCESS
echo "======= WxMinigame pipeline done ======="
