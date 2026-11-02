#!/usr/bin/env bash
# iOS commercial pipeline: Steps 1-3 (shared) + Xcode export + IPA OSS + TestFlight.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/commercial_pipeline_common.sh"
. "$SCRIPT_DIR/commercial_pipeline_unity.sh"
# shellcheck disable=SC1091
[ -f "$SCRIPT_DIR/jenkins_build_step_push.sh" ] && . "$SCRIPT_DIR/jenkins_build_step_push.sh"
[ -n "${JENKINS_HOME:-}" ] && [ -f "${JENKINS_HOME}/.apk-site-env" ] && . "${JENKINS_HOME}/.apk-site-env"

export APK_BUILD_ENABLED="${APK_BUILD_ENABLED:-false}"
export RELEASE_PLATFORM="${RELEASE_PLATFORM:-iOS}"
export IOS_BUILD_ENABLED="${IOS_BUILD_ENABLED:-true}"
export EXTERNAL_UPLOAD_TESTFLIGHT="${EXTERNAL_UPLOAD_TESTFLIGHT:-true}"

_log_ios_stage() {
  local step="$1"
  local title="$2"
  local detail="${3:-}"
  echo ""
  echo "=============================="
  echo "[阶段 ${step}] ${title}"
  echo "说明: ${detail}"
  echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=============================="
  echo "[ios] ${title}"
  if type _pipeline_push_build_step >/dev/null 2>&1; then
    _pipeline_push_build_step "$step" "running" "$title" "$detail" || true
  fi
}

_finish_ios_stage() {
  local step="$1"
  local title="$2"
  local detail="${3:-完成}"
  if type _pipeline_push_build_step >/dev/null 2>&1; then
    _pipeline_push_build_step "$step" "success" "$title" "$detail" || true
  fi
}

_fail_ios_stage() {
  local step="$1"
  local title="$2"
  local detail="${3:-失败}"
  if type _pipeline_push_build_step >/dev/null 2>&1; then
    _pipeline_push_build_step "$step" "failed" "$title" "$detail" || true
  fi
}

echo "======= iOS Commercial Pipeline ======="
bash "$SCRIPT_DIR/commercial_android_pipeline.sh"

if [ "${IOS_BUILD_ENABLED:-false}" != "true" ]; then
  echo "[ios] iOS base package skipped"
  _pipeline_notify_build_complete SUCCESS
  exit 0
fi

_log_ios_stage "5" "iOS Xcode 导出" "Unity ExportXcodeFromCommandLine"
IOS_ARGS="-releaseVersion \"${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}\""
IOS_ARGS="$IOS_ARGS -releaseEnvironment \"${RELEASE_ENVIRONMENT:-Development}\""
IOS_ARGS="$IOS_ARGS -releaseChannel \"${RELEASE_CHANNEL:-common}\""
IOS_ARGS="$IOS_ARGS -versionCode \"${VERSION_CODE:-1}\""
IOS_ARGS="$IOS_ARGS -appName \"${APP_NAME:-GomeKu}\""
[ -n "${IOS_SIGNING_PROFILE_ID:-}" ] && IOS_ARGS="$IOS_ARGS -signingProfileId \"${IOS_SIGNING_PROFILE_ID}\""
[ -n "${IOS_SIGNING_BUNDLE_ID:-}" ] && IOS_ARGS="$IOS_ARGS -bundleId \"${IOS_SIGNING_BUNDLE_ID}\""

if ! _run_unity iOSBuildScript.ExportXcodeFromCommandLine $IOS_ARGS; then
  _fail_ios_stage "5" "iOS Xcode 导出" "ExportXcode 失败"
  exit $?
fi
echo "Step 5 完成"
_finish_ios_stage "5" "iOS Xcode 导出" "Step 5 完成"

_log_ios_stage "6" "IPA 归档导出" "xcodebuild archive + export IPA"
ARCHIVE_ARGS="-releaseVersion \"${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}\""
ARCHIVE_ARGS="$ARCHIVE_ARGS -versionCode \"${VERSION_CODE:-1}\""
ARCHIVE_ARGS="$ARCHIVE_ARGS -appName \"${APP_NAME:-GomeKu}\""
if ! _run_unity XcodeArchiveCli.ExportIpaFromCommandLine $ARCHIVE_ARGS; then
  _fail_ios_stage "6" "IPA 归档导出" "ExportIpa 失败"
  exit $?
fi

IPA_FILE="${IPA_FILE:-}"
if [ -z "$IPA_FILE" ] || [ ! -f "$IPA_FILE" ]; then
  IPA_SEARCH="${OUTPUT_BASE_DIR:-${ARTIFACT_LANDING_DIR:-}}"
  IPA_FILE=$(find "$IPA_SEARCH" -name "*.ipa" -type f 2>/dev/null | head -n 1 || true)
fi
if [ -z "$IPA_FILE" ] || [ ! -f "$IPA_FILE" ]; then
  echo "ERROR: IPA not found"
  _fail_ios_stage "6" "IPA 归档导出" "IPA not found"
  exit 1
fi
export IPA_FILE
echo "[ios] IPA: $IPA_FILE"
echo "Step 6 完成"
_finish_ios_stage "6" "IPA 归档导出" "Step 6 完成"

_log_ios_stage "7" "IPA 落盘/OSS" "archive_build_artifact.py"
PY=$(_pipeline_resolve_python)
ARCHIVE="$SCRIPT_DIR/archive_build_artifact.py"
if [ -n "$PY" ] && [ -f "$ARCHIVE" ]; then
  export ARTIFACT_TYPE=ipa
  export ARTIFACT_FILE="$IPA_FILE"
  if ! $PY "$ARCHIVE"; then
    _fail_ios_stage "7" "IPA 落盘/OSS" "archive_build_artifact 失败"
    exit 1
  fi
fi
echo "Step 7 完成"
_finish_ios_stage "7" "IPA 落盘/OSS" "Step 7 完成"

if [ "${EXTERNAL_UPLOAD_TESTFLIGHT:-false}" = "true" ]; then
  _log_ios_stage "8" "TestFlight 上传" "upload_testflight.py"
  UP="$SCRIPT_DIR/upload_testflight.py"
  if [ -n "$PY" ] && [ -f "$UP" ]; then
    $PY "$UP" || echo "WARN: TestFlight upload failed (non-fatal if ASC not configured)"
  fi
  echo "Step 8 完成"
  _finish_ios_stage "8" "TestFlight 上传" "Step 8 完成"
else
  echo "Step 8 (TestFlight) 已跳过"
fi

_pipeline_notify_build_complete SUCCESS
echo "======= iOS pipeline done ======="
