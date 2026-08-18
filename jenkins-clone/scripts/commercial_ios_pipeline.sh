#!/usr/bin/env bash
# iOS commercial pipeline: Steps 1-3 (shared) + Xcode export + IPA OSS + TestFlight.
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
. "$SCRIPT_DIR/commercial_pipeline_common.sh"
. "$SCRIPT_DIR/commercial_pipeline_unity.sh"

export APK_BUILD_ENABLED="${APK_BUILD_ENABLED:-false}"
export RELEASE_PLATFORM="${RELEASE_PLATFORM:-iOS}"
export IOS_BUILD_ENABLED="${IOS_BUILD_ENABLED:-true}"
export EXTERNAL_UPLOAD_TESTFLIGHT="${EXTERNAL_UPLOAD_TESTFLIGHT:-true}"

echo "======= iOS Commercial Pipeline ======="
bash "$SCRIPT_DIR/commercial_android_pipeline.sh"

_log_ios() { echo "[ios] $*"; }

if [ "${IOS_BUILD_ENABLED:-false}" != "true" ]; then
  _log_ios "iOS base package skipped"
  _pipeline_notify_build_complete SUCCESS
  exit 0
fi

_log_ios "Step 5: Unity iOS Xcode export"
IOS_ARGS="-releaseVersion \"${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}\""
IOS_ARGS="$IOS_ARGS -releaseEnvironment \"${RELEASE_ENVIRONMENT:-Development}\""
IOS_ARGS="$IOS_ARGS -releaseChannel \"${RELEASE_CHANNEL:-common}\""
IOS_ARGS="$IOS_ARGS -versionCode \"${VERSION_CODE:-1}\""
IOS_ARGS="$IOS_ARGS -appName \"${APP_NAME:-GomeKu}\""
[ -n "${IOS_SIGNING_PROFILE_ID:-}" ] && IOS_ARGS="$IOS_ARGS -signingProfileId \"${IOS_SIGNING_PROFILE_ID}\""
[ -n "${IOS_SIGNING_BUNDLE_ID:-}" ] && IOS_ARGS="$IOS_ARGS -bundleId \"${IOS_SIGNING_BUNDLE_ID}\""

_run_unity iOSBuildScript.ExportXcodeFromCommandLine $IOS_ARGS || exit $?

_log_ios "Step 6: xcodebuild archive + export IPA"
ARCHIVE_ARGS="-releaseVersion \"${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}\""
ARCHIVE_ARGS="$ARCHIVE_ARGS -versionCode \"${VERSION_CODE:-1}\""
ARCHIVE_ARGS="$ARCHIVE_ARGS -appName \"${APP_NAME:-GomeKu}\""
_run_unity XcodeArchiveCli.ExportIpaFromCommandLine $ARCHIVE_ARGS || exit $?

IPA_FILE="${IPA_FILE:-}"
if [ -z "$IPA_FILE" ] || [ ! -f "$IPA_FILE" ]; then
  IPA_SEARCH="${OUTPUT_BASE_DIR:-${ARTIFACT_LANDING_DIR:-}}"
  IPA_FILE=$(find "$IPA_SEARCH" -name "*.ipa" -type f 2>/dev/null | head -n 1)
fi
if [ -z "$IPA_FILE" ] || [ ! -f "$IPA_FILE" ]; then
  echo "ERROR: IPA not found"
  exit 1
fi
export IPA_FILE
_log_ios "IPA: $IPA_FILE"

_log_ios "Step 7: OSS backup + local landing"
PY=$(_pipeline_resolve_python)
ARCHIVE="$SCRIPT_DIR/archive_build_artifact.py"
if [ -n "$PY" ] && [ -f "$ARCHIVE" ]; then
  export ARTIFACT_TYPE=ipa
  export ARTIFACT_FILE="$IPA_FILE"
  $PY "$ARCHIVE" || exit 1
fi

if [ "${EXTERNAL_UPLOAD_TESTFLIGHT:-false}" = "true" ]; then
  _log_ios "Step 8: TestFlight upload"
  UP="$SCRIPT_DIR/upload_testflight.py"
  if [ -n "$PY" ] && [ -f "$UP" ]; then
    $PY || echo "WARN: TestFlight upload failed (non-fatal if ASC not configured)"
  fi
fi

_pipeline_notify_build_complete SUCCESS
echo "======= iOS pipeline done ======="
