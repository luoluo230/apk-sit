#!/bin/bash
# APK 下载站 - 一键部署脚本 (macOS/Linux)
# 功能：自动创建虚拟环境、安装依赖、启动服务、配置开机自启（适用于云服务器）

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
# Jenkins 认证（触发构建报 403 时需配置）：复制 .env.example 为 .env 并填写 JENKINS_USER、JENKINS_TOKEN
[ -f .env ] && source .env

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

echo -e "${GREEN}╔══════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║        📦 APK 下载站 - 一键部署脚本 (macOS/Linux)         ║${NC}"
echo -e "${GREEN}╚══════════════════════════════════════════════════════════╝${NC}"
echo ""

# 检查 Python
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ 错误：未找到 Python 3${NC}"
    echo "请先安装 Python 3.8+（如：Ubuntu 上执行 sudo apt update && sudo apt install -y python3 python3-venv）"
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2)
echo -e "${GREEN}✅ Python 版本：${PYTHON_VERSION}${NC}"

# 创建虚拟环境并安装依赖（真正一键：云服务器推荐）
VENV_DIR="$SCRIPT_DIR/venv"
VENV_PY="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

if [ ! -d "$VENV_DIR" ]; then
    echo -e "${YELLOW}⚙️  未检测到虚拟环境，正在创建 venv...${NC}"
    python3 -m venv "$VENV_DIR"
    echo -e "${GREEN}✅ 已创建虚拟环境：$VENV_DIR${NC}"
fi

echo -e "${YELLOW}⚙️  正在安装 Python 依赖（requirements.txt / requirements-prod.txt）...${NC}"
"$VENV_PY" -m pip install --upgrade pip >/dev/null
"$VENV_PIP" install -r requirements.txt
if [ -f "requirements-prod.txt" ]; then
    "$VENV_PIP" install -r requirements-prod.txt
fi
echo -e "${GREEN}✅ Python 依赖安装完成${NC}"

# 统一使用 .env（应用只读 .env）
if [ ! -f ".env" ]; then
    if [ -f ".env.example" ]; then
        cp .env.example .env
        echo -e "${GREEN}✅ 已从 .env.example 创建 .env${NC}"
        echo -e "${YELLOW}提示：请按需编辑 .env（APK_DIR、端口、外网 PUBLIC_URL 等）${NC}"
    else
        echo -e "${YELLOW}⚠️  无 .env 且无 .env.example，将使用 config.py 默认值${NC}"
    fi
fi
[ -f .env ] && set -a && source .env && set +a

# 检查 Builds 目录（从 .env 或默认）
APK_DIR="${APK_DIR:-$SCRIPT_DIR}"
if [ -f ".env" ]; then
    APK_DIR=$(grep "^APK_DIR=" .env 2>/dev/null | head -1 | cut -d'=' -f2- | tr -d '"' | tr -d "'" | xargs)
fi
[ -z "$APK_DIR" ] && APK_DIR="$SCRIPT_DIR/data/apk"
if [ ! -d "$APK_DIR" ]; then
    echo -e "${YELLOW}⚠️  APK 目录不存在：$APK_DIR${NC}"
    echo "是否创建？(y/n)"
    read -r answer
    if [ "$answer" = "y" ]; then
        mkdir -p "$APK_DIR"
        echo -e "${GREEN}✅ 目录已创建${NC}"
    fi
fi

# 启动服务（开发/调试用：直接运行 Flask 应用）
start_service() {
    echo -e "${GREEN}🚀 启动服务（开发模式）...${NC}"
    "$VENV_PY" app_new.py
}

# 确保 logs 目录存在
mkdir -p logs

# 后台启动（云服务器默认用这个即可）
start_background() {
    echo -e "${GREEN}🚀 后台启动服务（使用虚拟环境）...${NC}"
    nohup "$VENV_PY" app_new.py >> logs/startup.log 2>&1 &
    echo $! > logs/app.pid
    echo -e "${GREEN}✅ 服务已启动 (PID: $(cat logs/app.pid))${NC}"
    echo -e "${GREEN}📄 日志：logs/startup.log${NC}"
}

# 停止服务
stop_service() {
    if [ -f "logs/app.pid" ]; then
        PID=$(cat logs/app.pid)
        if ps -p "$PID" > /dev/null; then
            echo -e "${YELLOW}⏹️  停止服务 (PID: $PID)...${NC}"
            kill "$PID"
            rm -f logs/app.pid
            echo -e "${GREEN}✅ 服务已停止${NC}"
        else
            echo -e "${YELLOW}⚠️  服务未运行${NC}"
        fi
    else
        echo -e "${YELLOW}⚠️  未找到 PID 文件${NC}"
    fi
}

# 配置开机自启 (macOS)
setup_autostart() {
    echo -e "${YELLOW}配置开机自启...${NC}"
    
    LAUNCHAGENT_DIR="$HOME/Library/LaunchAgents"
    LAUNCHAGENT_PLIST="$LAUNCHAGENT_DIR/com.apksite.app.plist"
    
    mkdir -p "$LAUNCHAGENT_DIR"
    
    cat > "$LAUNCHAGENT_PLIST" << EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
    <key>Label</key>
    <string>com.apksite.app</string>
    <key>ProgramArguments</key>
    <array>
        <string>/usr/bin/python3</string>
        <string>$SCRIPT_DIR/app_new.py</string>
    </array>
    <key>WorkingDirectory</key>
    <string>$SCRIPT_DIR</string>
    <key>RunAtLoad</key>
    <true/>
    <key>KeepAlive</key>
    <true/>
    <key>StandardOutPath</key>
    <string>$SCRIPT_DIR/logs/stdout.log</string>
    <key>StandardErrorPath</key>
    <string>$SCRIPT_DIR/logs/stderr.log</string>
</dict>
</plist>
EOF
    
    # 加载 LaunchAgent
    launchctl unload "$LAUNCHAGENT_PLIST" 2>/dev/null || true
    launchctl load "$LAUNCHAGENT_PLIST"
    
    echo -e "${GREEN}✅ 开机自启已配置${NC}"
}

# 主菜单
case "${1:-menu}" in
    start)
        start_service
        ;;
    start-bg)
        start_background
        ;;
    stop)
        stop_service
        ;;
    restart)
        stop_service
        sleep 1
        start_background
        ;;
    autostart)
        setup_autostart
        ;;
    menu)
        echo ""
        echo "请选择操作:"
        echo "  1) 直接启动 (前台)"
        echo "  2) 后台启动"
        echo "  3) 停止服务"
        echo "  4) 重启服务"
        echo "  5) 配置开机自启"
        echo "  6) 查看日志"
        echo "  0) 退出"
        echo ""
        read -p "请输入选项 [1-6]: " choice
        
        case $choice in
            1) start_service ;;
            2) start_background ;;
            3) stop_service ;;
            4) stop_service; sleep 1; start_background ;;
            5) setup_autostart ;;
            6) tail -f logs/app_*.log 2>/dev/null || echo "日志文件不存在" ;;
            *) echo "退出" ;;
        esac
        ;;
    *)
        echo "未知命令：$1"
        echo "用法：./deploy.sh [start|stop|restart|autostart|menu]"
        ;;
esac
