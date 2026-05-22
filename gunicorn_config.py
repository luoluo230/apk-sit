# -*- coding: utf-8 -*-
"""
APK 下载中心 - Gunicorn 生产配置

用法：
  gunicorn -c gunicorn_config.py app_new:app

或：
  gunicorn -c gunicorn_config.py app_new:app --bind 127.0.0.1:5003
"""

import os
import multiprocessing

# 绑定地址（Nginx 反向代理时仅监听本地）
bind = os.getenv("GUNICORN_BIND", "127.0.0.1:5003")

# Worker 数
workers = int(os.getenv("GUNICORN_WORKERS", multiprocessing.cpu_count() * 2 + 1))

# Worker 类型
worker_class = "sync"

# 超时（秒）
timeout = int(os.getenv("GUNICORN_TIMEOUT", "120"))

# 日志
_script_dir = os.path.dirname(os.path.abspath(__file__))
_log_dir = os.path.join(_script_dir, "logs")
os.makedirs(_log_dir, exist_ok=True)
accesslog = os.path.join(_log_dir, "gunicorn_access.log")
errorlog = os.path.join(_log_dir, "gunicorn_error.log")
loglevel = os.getenv("GUNICORN_LOG_LEVEL", "info")

proc_name = "apk-site"
chdir = _script_dir
