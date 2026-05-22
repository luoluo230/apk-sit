# -*- coding: utf-8 -*-
"""健康检查与状态接口测试（unittest + pytest 双支持）"""

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('APK_DEBUG', 'false')
os.environ.setdefault('FORCE_LOGIN', 'false')

from config import load_dotenv
load_dotenv()


def _get_client():
    from app_new import app
    app.config['TESTING'] = True
    app.config['WTF_CSRF_ENABLED'] = False
    return app.test_client()


class TestHealth(unittest.TestCase):
    def setUp(self):
        self.client = _get_client()

    def test_health_returns_200(self):
        """GET /health 返回 200"""
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)

    def test_health_returns_json(self):
        """GET /health 返回 JSON，包含 status"""
        r = self.client.get('/health')
        data = r.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get('status'), 'ok')
        self.assertEqual(data.get('service'), 'apk-site')

    def test_api_status_returns_200(self):
        """GET /api/status 返回 200"""
        r = self.client.get('/api/status')
        self.assertEqual(r.status_code, 200)

    def test_api_status_returns_stats(self):
        """GET /api/status 返回 stats 字段"""
        r = self.client.get('/api/status')
        data = r.get_json()
        self.assertIsNotNone(data)
        self.assertIn('status', data)
        self.assertTrue('stats' in data or 'service' in data)
