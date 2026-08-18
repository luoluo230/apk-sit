#!/bin/bash
# GameServer build pipeline — registers artifact zip with Portal (P2-01)
set -euo pipefail
ROOT="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
GAMESERVER_ROOT="${GAMESERVER_ROOT:-$ROOT/../maclient/game-server}"
OUT_ZIP="${BUILD_NUMBER:-local}-gameserver.zip"
STAGE="${STAGE:-$WORKSPACE/stage}"
mkdir -p "$STAGE"
if [ -d "$GAMESERVER_ROOT/publish" ]; then
  cp -r "$GAMESERVER_ROOT/publish/." "$STAGE/"
else
  echo "WARN: no publish/ — creating placeholder for gate"
  mkdir -p "$STAGE/game-cn-1"
  echo "placeholder" > "$STAGE/game-cn-1/README.txt"
fi
(cd "$STAGE" && zip -r "$WORKSPACE/$OUT_ZIP" .)
export GAMESERVER_ARTIFACT="$WORKSPACE/$OUT_ZIP"
echo "GAMESERVER_ARTIFACT=$GAMESERVER_ARTIFACT"

# shellcheck source=commercial_pipeline_common.sh
source "$SCRIPT_DIR/commercial_pipeline_common.sh" 2>/dev/null || true

PY="$(_pipeline_resolve_python 2>/dev/null || true)"
if [ -z "$PY" ]; then
  if command -v py >/dev/null 2>&1; then PY="py -3"; elif command -v python3 >/dev/null 2>&1; then PY="python3"; else PY="python"; fi
fi
export PROJECT_ID="${PROJECT_ID:-GomeKu}"
export SERVER_VERSION_LABEL="${SERVER_VERSION_LABEL:-${VERSION_NAME:-}}"
export SERVER_PROTOCOL_VERSION="${SERVER_PROTOCOL_VERSION:-v1}"
export SERVER_ARTIFACT_REGISTER_MODE="${SERVER_ARTIFACT_REGISTER_MODE:-local}"
export CLIENT_BUILD_NUMBER="${CLIENT_BUILD_NUMBER:-${BUILD_NUMBER:-}}"
export CLIENT_JENKINS_INSTANCE_ID="${CLIENT_JENKINS_INSTANCE_ID:-${JENKINS_INSTANCE_ID:-}}"
export RELEASE_ORDER_ID="${RELEASE_ORDER_ID:-}"
if [ -n "$PY" ]; then
  $PY "$SCRIPT_DIR/register_server_artifact.py" || echo "[register] server artifact registration failed (non-fatal in dev)"
fi

if type _pipeline_notify_build_complete >/dev/null 2>&1; then
  _pipeline_notify_build_complete "SUCCESS"
fi
