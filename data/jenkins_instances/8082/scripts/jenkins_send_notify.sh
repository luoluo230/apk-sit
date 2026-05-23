#!/bin/bash
# Jenkins 构建通知脚本（飞书）：直接用本次构建参数拼下载链接，不扫描磁盘
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-env" ] && . "${JENKINS_HOME}/.apk-site-env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

INPUT_VER="$1"
INPUT_BUILD="$2"
APP_NAME="${APP_NAME:-GameKu}"

# 版本号、构建号：优先用传入参数（即本次构建），否则用 Jenkins 环境变量
VERSION="${INPUT_VER:-$VERSION_NAME}"
[ -z "$VERSION" ] && VERSION="Unknown"
BUILD_NUM="${INPUT_BUILD:-$BUILD_NUMBER}"
[ -z "$BUILD_NUM" ] && BUILD_NUM="Unknown"

# 包名与下载链接：与 Jenkins 日志里一致，直接用构建参数拼，无需扫描
FNAME="${APP_NAME}_${VERSION}.apk"
DOWNLOAD_URL="${APKSITE_BASE_URL:-http://127.0.0.1:5003}/pub/download/${FNAME}"
DOWNLOAD_IP="${DOWNLOAD_IP:-$(echo "$APKSITE_BASE_URL" | sed -n 's|.*://\([^:/]*\).*|\1|p')}"

# 飞书 Webhook：优先读该实例的 .apk-site-feishu
FEISHU_WEBHOOK=""
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-feishu" ] && . "${JENKINS_HOME}/.apk-site-feishu"
WEBHOOK="${FEISHU_WEBHOOK:-}"
[ -z "$WEBHOOK" ] && exit 0

TEXT="🚀 Jenkins 构建完成
✅ 状态：成功
📦 版本：${VERSION}
🔢 构建号：${BUILD_NUM}
📱 包名：${FNAME}
📥 下载：${DOWNLOAD_URL}
🌐 IP: ${DOWNLOAD_IP}"

echo "$TEXT" | python3 "${SCRIPT_DIR}/feishu_send.py" "$WEBHOOK" || true
exit 0
