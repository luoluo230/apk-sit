#!/bin/bash
# APK 下载服务启动器；路径由 .apk-site-env 或脚本所在目录推导，复制到 apk-site 即用
JENKINS_CLONE="$(cd "$(dirname "$0")" && pwd)"
[ -f "${JENKINS_CLONE}/.apk-site-env" ] && . "${JENKINS_CLONE}/.apk-site-env"
SCRIPT_DIR="${JENKINS_CLONE}/scripts"
LOG_DIR="${JENKINS_CLONE}/logs"

mkdir -p "$LOG_DIR"
pkill -f "http.server 8888" 2>/dev/null
sleep 1

echo "🚀 启动 APK 下载服务..."
cd "$SCRIPT_DIR"
nohup bash start_apk_server.sh > "$LOG_DIR/startup.log" 2>&1 &

echo "✅ 服务已启动 (PID: $!)"
