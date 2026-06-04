#!/bin/bash
# 启动 APK 下载服务器（路径由 apk-site 写入 .apk-site-env，复制到 apk-site 即用）
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-env" ] && . "${JENKINS_HOME}/.apk-site-env"
[ -z "$JENKINS_CLONE" ] && JENKINS_CLONE="$(cd "$(dirname "$0")/.." && pwd)"
SCRIPT_DIR="${JENKINS_CLONE}/scripts"
LOG_DIR="${JENKINS_CLONE}/logs"
APK_DIR="${APK_DIR:-$HOME/Builds}"

mkdir -p "$LOG_DIR"
LOG_FILE="$LOG_DIR/apk_server.log"
ERR_FILE="$LOG_DIR/apk_server.err"
> "$LOG_FILE"
> "$ERR_FILE"

echo "🚀 启动 APK 下载服务..."
echo "📂 资源目录：$APK_DIR"
echo "📝 日志文件：$LOG_FILE"

cd "$APK_DIR" || exit 1
exec python3 -m http.server 8888 --bind 0.0.0.0 > "$LOG_FILE" 2> "$ERR_FILE"
