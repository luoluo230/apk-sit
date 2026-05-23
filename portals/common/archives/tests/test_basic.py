# -*- coding: utf-8 -*-
"""基础测试（使用 unittest，无需 pytest）"""

import unittest
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 测试环境
os.environ.setdefault('APK_DEBUG', 'false')
os.environ.setdefault('FORCE_LOGIN', 'false')

from config import load_dotenv
load_dotenv()


class TestBasic(unittest.TestCase):
    def setUp(self):
        from app_new import app
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.client = app.test_client()

    def test_health(self):
        r = self.client.get('/health')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIsNotNone(data)
        self.assertEqual(data.get('status'), 'ok')

    def test_api_status(self):
        r = self.client.get('/api/status')
        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertIn('status', data)
        self.assertIn('stats', data)

    def test_api_docs(self):
        r = self.client.get('/api/docs')
        self.assertEqual(r.status_code, 200)
        self.assertGreater(len(r.data), 100)

    def test_404(self):
        r = self.client.get('/nonexistent-page-test')
        self.assertEqual(r.status_code, 404)
        self.assertGreater(len(r.data), 100)
        self.assertIn(b'<!DOCTYPE html>', r.data)


if __name__ == '__main__':
    unittest.main()
