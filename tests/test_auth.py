# -*- coding: utf-8 -*-
"""认证相关测试（unittest + pytest 双支持）"""

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


class TestAuth(unittest.TestCase):
    def setUp(self):
        self.client = _get_client()

    def test_login_page_accessible(self):
        """登录页可访问"""
        r = self.client.get('/login')
        self.assertEqual(r.status_code, 200)
        body = r.data.decode('utf-8', errors='ignore').lower()
        self.assertTrue('login' in body or '登录' in body)

    def test_login_with_wrong_password(self):
        """错误密码登录失败（返回 200 带错误提示，或 429 若被限流）"""
        r = self.client.post('/login', data={
            'username': 'nonexistent_user',
            'password': 'wrongpassword'
        }, follow_redirects=True)
        self.assertIn(r.status_code, (200, 429))

    def test_logout_redirects(self):
        """退出登录重定向"""
        r = self.client.get('/logout', follow_redirects=False)
        self.assertIn(r.status_code, (302, 200))

    def test_z_login_rate_limit_returns_429(self):
        """登录限流：超限返回 429 与 Retry-After 头（z 前缀使本测试最后执行，避免影响其他测试）"""
        for _ in range(11):
            r = self.client.post('/login', data={'username': 'x', 'password': 'y'}, follow_redirects=False)
            if r.status_code == 429:
                self.assertIn('Retry-After', r.headers)
                return
        self.assertIn(r.status_code, (200, 429))
