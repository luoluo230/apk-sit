#!/bin/bash
# APK 下载网站启动脚本
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LOG_FILE="$SCRIPT_DIR/logs/website.log"
PID_FILE="$SCRIPT_DIR/logs/website.pid"
PORT=5001

# 1. 停止旧进程
if [ -f "$PID_FILE" ]; then
    old_pid=$(cat "$PID_FILE")
    if ps -p $old_pid > /dev/null; then
        echo "🛑 停止旧进程 (PID: $old_pid)"
        kill $old_pid
        sleep 2
    fi
fi
pkill -f "app.py" 2>/dev/null

# 2. 启动新进程
echo "🚀 启动 APK 下载网站..."
cd "$SCRIPT_DIR"
nohup python3 app.py > "$LOG_FILE" 2>&1 &
echo $! > "$PID_FILE"

# 3. 验证
sleep 3
if ps -p $(cat "$PID_FILE") > /dev/null; then
    echo "✅ 网站已启动 (PID: $(cat $PID_FILE))"
    echo "🌐 访问地址：http://localhost:$PORT"
else
    echo "❌ 启动失败，查看日志：$LOG_FILE"
fi
