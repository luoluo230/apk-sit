#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APK 下载站 - 自动扫描 Builds 目录并生成下载列表
依赖：pip install flask
"""
import os
import re
from datetime import datetime
from flask import Flask, render_template_string, send_from_directory, abort

app = Flask(__name__)

# 配置
APK_DIR = os.getenv("APK_DIR", os.path.join(os.path.dirname(__file__), "..", "..", "data", "apk"))
PORT = 5001

# HTML 模板 (包含 TailwindCSS 样式)
HTML_TEMPLATE = """
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>GameKu APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <style>
        body { background-color: #f3f4f6; }
        .apk-card { transition: all 0.2s; }
        .apk-card:hover { transform: translateY(-2px); box-shadow: 0 10px 15px -3px rgba(0, 0, 0, 0.1); }
    </style>
</head>
<body class="text-gray-800">
    <div class="container mx-auto px-4 py-8 max-w-4xl">
        <header class="mb-8 text-center">
            <h1 class="text-3xl font-bold text-blue-600 mb-2">🚀 GameKu APK 下载中心</h1>
            <p class="text-gray-500">自动同步最新构建版本</p>
        </header>

        {% if files %}
        <div class="grid gap-4">
            {% for file in files %}
            <div class="apk-card bg-white rounded-lg shadow p-4 flex flex-col md:flex-row justify-between items-center border-l-4 border-blue-500">
                <div class="mb-2 md:mb-0 text-center md:text-left">
                    <h3 class="text-lg font-bold text-gray-800">{{ file.name }}</h3>
                    <p class="text-sm text-gray-500 mt-1">
                        📅 {{ file.date }} &nbsp;|&nbsp; 💾 {{ file.size }}
                    </p>
                </div>
                <a href="/download/{{ file.name }}" 
                   class="px-6 py-2 bg-blue-600 text-white rounded-full hover:bg-blue-700 transition shadow-md flex items-center">
                   <svg class="w-4 h-4 mr-2" fill="none" stroke="currentColor" viewBox="0 0 24 24"><path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M4 16v1a3 3 0 003 3h10a3 3 0 003-3v-1m-4-4l-4 4m0 0l-4-4m4 4V4"></path></svg>
                   下载
                </a>
            </div>
            {% endfor %}
        </div>
        {% else %}
        <div class="text-center text-gray-500 py-10">
            <p>暂无可用安装包</p>
        </div>
        {% endif %}
        
        <footer class="mt-12 text-center text-gray-400 text-sm">
            <p>Powered by Jenkins & Flask</p>
        </footer>
    </div>
</body>
</html>
"""

def get_file_size(size_bytes):
    """格式化文件大小"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size_bytes < 1024.0:
            return f"{size_bytes:.1f} {unit}"
        size_bytes /= 1024.0
    return f"{size_bytes:.1f} TB"

def parse_version(filename):
    """从文件名解析版本信息 (可选优化)"""
    return filename

@app.route('/')
def index():
    if not os.path.exists(APK_DIR):
        return f"错误：目录 {APK_DIR} 不存在", 500
    
    files = []
    try:
        # 扫描目录
        for fname in os.listdir(APK_DIR):
            if fname.endswith('.apk'):
                fpath = os.path.join(APK_DIR, fname)
                stat = os.stat(fpath)
                files.append({
                    'name': fname,
                    'size': get_file_size(stat.st_size),
                    'date': datetime.fromtimestamp(stat.st_mtime).strftime('%Y-%m-%d %H:%M'),
                    'timestamp': stat.st_mtime
                })
    except Exception as e:
        return f"扫描文件出错：{e}", 500

    # 按时间倒序排序
    files.sort(key=lambda x: x['timestamp'], reverse=True)
    
    return render_template_string(HTML_TEMPLATE, files=files)

@app.route('/download/<filename>')
def download(filename):
    # 安全校验，防止目录遍历
    if '..' in filename or filename.startswith('/'):
        abort(403)
    try:
        return send_from_directory(APK_DIR, filename, as_attachment=True)
    except FileNotFoundError:
        abort(404)

if __name__ == '__main__':
    print(f"🚀 启动 APK 下载服务...")
    print(f"📂 扫描目录：{APK_DIR}")
    print(f"🌐 访问地址：http://localhost:{PORT}")
    # host='0.0.0.0' 允许局域网访问
    app.run(host='0.0.0.0', port=PORT, debug=False)
