#!/bin/bash
# 修复 apk-site 触发构建 403：把 Jenkins 设为不校验安全（无登录、无 CSRF）
# 使用：先停掉 Jenkins，再运行本脚本，然后启动 Jenkins。
cd "$(dirname "$0")"
CONFIG="config.xml"
if [ ! -f "$CONFIG" ]; then
  echo "未找到 $CONFIG"
  exit 1
fi
cp "$CONFIG" "${CONFIG}.bak.$(date +%s)"
sed -i '' 's/<useSecurity>true<\/useSecurity>/<useSecurity>false<\/useSecurity>/' "$CONFIG"
sed -i '' '/<crumbIssuer class="hudson.security.csrf.DefaultCrumbIssuer">/,/<\/crumbIssuer>/d' "$CONFIG"
echo "已修改 $CONFIG：useSecurity=false，已删除 crumbIssuer。请启动 Jenkins（如 ./start_jenkins.sh）。"