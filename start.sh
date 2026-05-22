#!/bin/bash
# APK 下载站 - 快速启动脚本（使用 app_new.py 含构建管理等功能）
# 启动后会自动拉起 8888 直链下载服务，供飞书通知等链接使用
cd "$(dirname "${BASH_SOURCE[0]}")"
[ -f .env ] && source .env
python3 app_new.py
