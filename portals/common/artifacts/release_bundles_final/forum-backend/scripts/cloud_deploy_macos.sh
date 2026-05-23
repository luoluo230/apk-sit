#!/usr/bin/env bash
set -euo pipefail

APP_DIR="${APP_DIR:-$(cd "$(dirname "$0")/.." && pwd)}"
ADMIN_PORT="${ADMIN_PORT:-5003}"
PLAYER_PORT="${PLAYER_PORT:-5004}"
APK_DIR="${APK_DIR:-$APP_DIR/data/apk}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
PLIST_DIR="${HOME}/Library/LaunchAgents"
ADMIN_PLIST="com.apksite.admin.plist"
PLAYER_PLIST="com.apksite.player.plist"

mkdir -p "$APP_DIR/logs" "$APP_DIR/data" "$APK_DIR" "$PLIST_DIR"
cd "$APP_DIR"

if [ ! -f ".env" ] && [ -f ".env.example" ]; then
  cp ".env.example" ".env"
fi

if [ ! -d "venv" ]; then
  "$PYTHON_BIN" -m venv venv
fi

VENV_PY="$APP_DIR/venv/bin/python"
"$VENV_PY" -m pip install --upgrade pip
"$VENV_PY" -m pip install -r "$APP_DIR/requirements.txt"
if [ -f "$APP_DIR/requirements-prod.txt" ]; then
  "$VENV_PY" -m pip install -r "$APP_DIR/requirements-prod.txt"
fi

python_env_update() {
  "$VENV_PY" - "$APP_DIR/.env" <<'PY'
from pathlib import Path
import os

env_path = Path(__import__("sys").argv[1])
values = {
    "APK_DIR": os.environ["APK_DIR"],
    "ADMIN_PORT": os.environ["ADMIN_PORT"],
    "PLAYER_PORT": os.environ["PLAYER_PORT"],
    "APK_PORT": os.environ["ADMIN_PORT"],
    "USE_SQLITE": "true",
    "SQLITE_MIRROR_JSON": "false",
}
lines = []
if env_path.exists():
    lines = env_path.read_text(encoding="utf-8").splitlines()
out = []
seen = set()
for line in lines:
    if "=" in line and not line.lstrip().startswith("#"):
        key = line.split("=", 1)[0].strip()
        if key in values:
            out.append(f"{key}={values[key]}")
            seen.add(key)
            continue
    out.append(line)
for key, value in values.items():
    if key not in seen:
        out.append(f"{key}={value}")
env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
PY
}

export APK_DIR ADMIN_PORT PLAYER_PORT
python_env_update

"$VENV_PY" "$APP_DIR/scripts/migrate_json_to_sqlite.py"

cat > "$PLIST_DIR/$ADMIN_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.apksite.admin</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV_PY</string>
    <string>-u</string>
    <string>-m</string>
    <string>waitress</string>
    <string>--listen=0.0.0.0:$ADMIN_PORT</string>
    <string>admin_wsgi:app</string>
  </array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>APP_PORTAL_MODE</key><string>admin</string>
    <key>APK_PORT</key><string>$ADMIN_PORT</string>
    <key>ADMIN_PORT</key><string>$ADMIN_PORT</string>
    <key>PLAYER_PORT</key><string>$PLAYER_PORT</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$APP_DIR/logs/admin-portal.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/logs/admin-portal.err.log</string>
</dict>
</plist>
PLIST

cat > "$PLIST_DIR/$PLAYER_PLIST" <<PLIST
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.apksite.player</string>
  <key>ProgramArguments</key>
  <array>
    <string>$VENV_PY</string>
    <string>-u</string>
    <string>-m</string>
    <string>waitress</string>
    <string>--listen=0.0.0.0:$PLAYER_PORT</string>
    <string>player_wsgi:app</string>
  </array>
  <key>WorkingDirectory</key><string>$APP_DIR</string>
  <key>EnvironmentVariables</key>
  <dict>
    <key>APP_PORTAL_MODE</key><string>player</string>
    <key>APK_PORT</key><string>$PLAYER_PORT</string>
    <key>ADMIN_PORT</key><string>$ADMIN_PORT</string>
    <key>PLAYER_PORT</key><string>$PLAYER_PORT</string>
    <key>ENABLE_DOWNLOAD_FILE_SERVICE</key><string>false</string>
    <key>ENABLE_BACKGROUND_SCHEDULER</key><string>false</string>
  </dict>
  <key>RunAtLoad</key><true/>
  <key>KeepAlive</key><true/>
  <key>StandardOutPath</key><string>$APP_DIR/logs/player-portal.log</string>
  <key>StandardErrorPath</key><string>$APP_DIR/logs/player-portal.err.log</string>
</dict>
</plist>
PLIST

launchctl unload "$PLIST_DIR/$ADMIN_PLIST" >/dev/null 2>&1 || true
launchctl unload "$PLIST_DIR/$PLAYER_PLIST" >/dev/null 2>&1 || true
launchctl load "$PLIST_DIR/$ADMIN_PLIST"
launchctl load "$PLIST_DIR/$PLAYER_PLIST"

sleep 5
curl -fsS "http://127.0.0.1:$ADMIN_PORT/health" >/dev/null
curl -fsS "http://127.0.0.1:$PLAYER_PORT/health" >/dev/null

echo "Admin portal:  http://127.0.0.1:$ADMIN_PORT"
echo "Player portal: http://127.0.0.1:$PLAYER_PORT"
