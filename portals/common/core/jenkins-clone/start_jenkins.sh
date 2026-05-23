#!/bin/bash
# 启动 Jenkins 服务（使用本目录为 JENKINS_HOME，端口默认 8080）
# apk-site 构建管理会连接此端口，若改端口需同时设置 apk-site 的 JENKINS_PORT

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

export JENKINS_HOME="$SCRIPT_DIR"
PORT="${JENKINS_PORT:-8080}"

# 查找 jenkins.war：环境变量 JENKINS_WAR > 本目录 > 下载到本目录
WAR=""
if [ -n "$JENKINS_WAR" ] && [ -f "$JENKINS_WAR" ]; then
    WAR="$JENKINS_WAR"
elif [ -f "$SCRIPT_DIR/jenkins.war" ]; then
    WAR="$SCRIPT_DIR/jenkins.war"
elif [ -f "$SCRIPT_DIR/war/jenkins.war" ]; then
    WAR="$SCRIPT_DIR/war/jenkins.war"
fi

if [ -z "$WAR" ]; then
    echo "未找到 jenkins.war，尝试下载到 $SCRIPT_DIR/jenkins.war ..."
    if command -v curl >/dev/null 2>&1; then
        if curl -fL -o "$SCRIPT_DIR/jenkins.war" "https://get.jenkins.io/war-stable/latest/jenkins.war"; then
            WAR="$SCRIPT_DIR/jenkins.war"
            echo "下载完成。"
        fi
    fi
fi

if [ -z "$WAR" ] || [ ! -f "$WAR" ]; then
    echo "❌ 无法找到或下载 jenkins.war"
    echo "请手动下载后放到本目录："
    echo "  https://get.jenkins.io/war-stable/latest/jenkins.war"
    echo "或指定路径：JENKINS_WAR=/path/to/jenkins.war $0"
    exit 1
fi

echo "🚀 启动 Jenkins（端口 $PORT）"
echo "   访问：http://localhost:$PORT"
echo "   关闭：当前终端 Ctrl+C"
exec java -jar "$WAR" --httpPort="$PORT"
