# -*- coding: utf-8 -*-
from __future__ import annotations
"""Jenkins 多实例管理：端口检测、启动/停止、环境检查与一键部署、实例默认构建参数"""

import os
import sys
import socket
import subprocess
import platform
import uuid
import logging
import shutil
import urllib.request
from datetime import datetime
try:
    import winreg
except Exception:
    winreg = None

from config import Config, JENKINS_CLONE_DIR
from models.data import load_jenkins_instances, save_jenkins_instances, channels_db

logger = logging.getLogger(__name__)

from pathlib import Path

_PARTS = [
    "part_01.py",
    "part_02.py",
    "part_03.py",
    "part_04.py",
    "part_05.py",
    "part_06.py",
]

def _load_parts():
    folder = Path(__file__).resolve().parent / "jenkins"
    for name in _PARTS:
        path = folder / name
        code = path.read_text(encoding="utf-8")
        exec(compile(code, str(path), "exec"), globals())


_load_parts()
