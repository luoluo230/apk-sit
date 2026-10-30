#!/bin/bash
# Jenkins 构建通知：飞书 / 钉钉 / 企业微信（任一已配置则发送）
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-env" ] && . "${JENKINS_HOME}/.apk-site-env"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

INPUT_VER="$1"
INPUT_BUILD="$2"
APP_NAME="${APP_NAME:-GameKu}"

VERSION="${INPUT_VER:-$VERSION_NAME}"
[ -z "$VERSION" ] && VERSION="Unknown"
BUILD_NUM="${INPUT_BUILD:-$BUILD_NUMBER}"
[ -z "$BUILD_NUM" ] && BUILD_NUM="Unknown"

FNAME="${APP_NAME}_${VERSION}.apk"
DOWNLOAD_URL="${APKSITE_BASE_URL:-http://127.0.0.1:5003}/pub/download/${FNAME}"
DOWNLOAD_IP="${DOWNLOAD_IP:-$(echo "$APKSITE_BASE_URL" | sed -n 's|.*://\([^:/]*\).*|\1|p')}"

FEISHU_WEBHOOK=""
DINGTALK_WEBHOOK=""
WECOM_WEBHOOK=""
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-feishu" ] && . "${JENKINS_HOME}/.apk-site-feishu"
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-dingtalk" ] && . "${JENKINS_HOME}/.apk-site-dingtalk"
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-wecom" ] && . "${JENKINS_HOME}/.apk-site-wecom"

TEXT="Jenkins 构建完成
状态：成功
版本：${VERSION}
构建号：${BUILD_NUM}
包名：${FNAME}
下载：${DOWNLOAD_URL}
IP: ${DOWNLOAD_IP}"

SENT=0
PY=""
command -v python3 >/dev/null 2>&1 && PY=python3
[ -z "$PY" ] && command -v python >/dev/null 2>&1 && PY=python

if [ -n "$FEISHU_WEBHOOK" ] && [ -n "$PY" ] && [ -f "${SCRIPT_DIR}/feishu_send.py" ]; then
  echo "$TEXT" | "$PY" "${SCRIPT_DIR}/feishu_send.py" "$FEISHU_WEBHOOK" || true
  SENT=1
fi
if [ -n "$DINGTALK_WEBHOOK" ] && [ -n "$PY" ] && [ -f "${SCRIPT_DIR}/dingtalk_send.py" ]; then
  echo "$TEXT" | "$PY" "${SCRIPT_DIR}/dingtalk_send.py" "$DINGTALK_WEBHOOK" || true
  SENT=1
fi
if [ -n "$WECOM_WEBHOOK" ] && [ -n "$PY" ] && [ -f "${SCRIPT_DIR}/wecom_send.py" ]; then
  echo "$TEXT" | "$PY" "${SCRIPT_DIR}/wecom_send.py" "$WECOM_WEBHOOK" || true
  SENT=1
fi

[ "$SENT" = "1" ] && exit 0
exit 0
