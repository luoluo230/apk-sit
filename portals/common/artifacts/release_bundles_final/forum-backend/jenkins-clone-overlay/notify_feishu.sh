#!/bin/bash
# Jenkins 构建后通知脚本；路径由 .apk-site-env 或 OUTPUT_BASE_DIR 提供
JENKINS_CLONE="$(cd "$(dirname "$0")" && pwd)"
[ -f "${JENKINS_CLONE}/.apk-site-env" ] && . "${JENKINS_CLONE}/.apk-site-env"
APK_DIR="${APK_DIR:-$OUTPUT_BASE_DIR}"
APK_DIR="${APK_DIR:-$HOME/Builds}"

BUILD_VERSION=${VERSION_NAME:-"Unknown"}
BUILD_STATUS=${BUILD_STATUS:-"Unknown"}
APK_PATH="${APK_DIR}/GameKu_${BUILD_VERSION}_*/GameKu_${BUILD_VERSION}.apk"

LATEST_APK=$(ls -t $APK_PATH 2>/dev/null | head -1)

DOWNLOAD_BASE=""
[ -f "${APK_DIR}/.apk-site-base-url" ] && DOWNLOAD_BASE=$(head -1 "${APK_DIR}/.apk-site-base-url" | tr -d '\r\n')
[ -z "$DOWNLOAD_BASE" ] && DOWNLOAD_BASE="http://127.0.0.1:5003"

if [ -n "$LATEST_APK" ]; then
    FNAME=$(basename "$LATEST_APK")
    MESSAGE="✅ 构建成功！版本：${BUILD_VERSION}\n下载：${DOWNLOAD_BASE}/pub/download/${FNAME}"
    echo "发送通知：$MESSAGE"
else
    echo "未找到 APK 文件，跳过通知"
fi
