# -*- coding: utf-8 -*-
"""pytest 配置与 fixture"""

import os
import sys
import tempfile
import shutil

# 确保项目根在 path 中
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试前设置独立数据目录，避免污染生产数据
TEST_DATA_DIR = os.path.join(tempfile.gettempdir(), 'apk_site_test_data')
os.environ['APK_DIR'] = os.path.join(TEST_DATA_DIR, 'apk')
os.makedirs(TEST_DATA_DIR, exist_ok=True)
os.makedirs(os.environ['APK_DIR'], exist_ok=True)


def pytest_configure(config):
    """pytest 配置：设置环境变量"""
    os.environ.setdefault('APK_DEBUG', 'false')
    os.environ.setdefault('FORCE_LOGIN', 'false')  # 测试时可选不强制登录


import pytest
from config import load_dotenv
load_dotenv()


@pytest.fixture
def app():
    """Flask 应用实例"""
    from app_new import app as flask_app
    flask_app.config['TESTING'] = True
    flask_app.config['WTF_CSRF_ENABLED'] = False
    return flask_app


@pytest.fixture
def client(app):
    """Flask 测试客户端"""
    return app.test_client()


@pytest.fixture
def runner(app):
    """Flask CLI 测试运行器"""
    return app.test_cli_runner()
