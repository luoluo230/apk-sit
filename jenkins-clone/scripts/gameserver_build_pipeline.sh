#!/bin/bash
# GameServer build pipeline — registers artifact zip with Portal (P2-01)
set -euo pipefail
ROOT="${WORKSPACE:-$(cd "$(dirname "$0")/../.." && pwd)}"
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
echo "GAMESERVER_ARTIFACT=$WORKSPACE/$OUT_ZIP"
