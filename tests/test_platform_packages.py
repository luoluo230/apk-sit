# -*- coding: utf-8 -*-
"""Android/iOS 安装包链路测试。"""

import io
import os
import sys
import tempfile
import unittest
import copy

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault('APK_DEBUG', 'false')
os.environ.setdefault('FORCE_LOGIN', 'false')

from config import load_dotenv
load_dotenv()


class TestPlatformPackages(unittest.TestCase):
    def setUp(self):
        from app_new import app
        app.config['TESTING'] = True
        app.config['WTF_CSRF_ENABLED'] = False
        self.app = app
        self.client = app.test_client()

    def test_api_status_returns_platform_breakdown(self):
        from config import Config

        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'GameKu_1.0.0.apk'), 'wb') as f:
                f.write(b'apk')
            with open(os.path.join(tmpdir, 'GameKu_1.0.0.ipa'), 'wb') as f:
                f.write(b'ipa')

            old_dir = Config.APK_DIR
            Config.APK_DIR = tmpdir
            try:
                r = self.client.get('/api/status')
            finally:
                Config.APK_DIR = old_dir

        self.assertEqual(r.status_code, 200)
        data = r.get_json()
        self.assertEqual(data['stats']['platforms']['android'], 1)
        self.assertEqual(data['stats']['platforms']['ios'], 1)
        self.assertEqual(data['stats']['package_count'], 2)

    def test_download_supports_ios_package(self):
        from config import Config

        with tempfile.TemporaryDirectory() as tmpdir:
            package_name = 'GameKu_1.0.1.ipa'
            with open(os.path.join(tmpdir, package_name), 'wb') as f:
                f.write(b'ios-package')

            old_dir = Config.APK_DIR
            Config.APK_DIR = tmpdir
            try:
                with self.client.session_transaction() as sess:
                    sess['user'] = 'admin'
                r = self.client.get('/download/' + package_name)
                payload = r.get_data()
                disposition = r.headers.get('Content-Disposition', '')
                status_code = r.status_code
                r.close()
            finally:
                Config.APK_DIR = old_dir

        self.assertEqual(status_code, 200)
        self.assertIn(package_name, disposition)
        self.assertEqual(payload, b'ios-package')

    def test_product_detail_shows_android_and_ios_downloads(self):
        from config import Config
        from models.data import products_db

        original_products = list(products_db)
        with tempfile.TemporaryDirectory() as tmpdir:
            with open(os.path.join(tmpdir, 'GameKu_2.0.0.apk'), 'wb') as f:
                f.write(b'apk')
            with open(os.path.join(tmpdir, 'GameKu_2.0.0.ipa'), 'wb') as f:
                f.write(b'ipa')

            products_db[:] = [{
                'id': 'gameku-product',
                'name': 'GameKu',
                'intro': 'test product',
                'project_id': 'GameKu',
                'cover_image': '',
                'gallery': [],
            }]

            old_dir = Config.APK_DIR
            Config.APK_DIR = tmpdir
            try:
                with self.client.session_transaction() as sess:
                    sess['user'] = 'admin'
                r = self.client.get('/product/gameku-product')
            finally:
                Config.APK_DIR = old_dir
                products_db[:] = original_products

        body = r.data.decode('utf-8', errors='ignore')
        self.assertEqual(r.status_code, 200)
        self.assertIn('Android', body)
        self.assertIn('iOS', body)
        self.assertIn('/download/GameKu_2.0.0.apk', body)
        self.assertIn('/download/GameKu_2.0.0.ipa', body)

    def test_project_version_create_persists_platform(self):
        from models.data import project_versions_db, projects_db, save_project_versions, save_projects

        original_versions = copy.deepcopy(project_versions_db.get('GomeKu'))
        original_project = copy.deepcopy(projects_db.get('GomeKu'))
        projects_db['GomeKu'] = original_project or {
            'name': 'GomeKu',
            'created_by': 'admin',
            'editors': ['admin'],
            'viewers': [],
        }
        project_versions_db['GomeKu'] = []
        try:
            with self.client.session_transaction() as sess:
                sess['user'] = 'admin'
            r = self.client.post('/admin/projects/GomeKu/versions/create', json={
                'channel': 'dev',
                'stage': 'dev',
                'platform': 'ios',
                'version_name': '3.0.0',
                'version_code': '300',
                'apk_path': 'ios/GameKu_3.0.0.ipa',
            })
            data = r.get_json()
            self.assertEqual(r.status_code, 200)
            self.assertEqual(data['version']['platform'], 'ios')
            self.assertEqual(data['version']['platform_label'], 'iOS')
        finally:
            if original_versions is None:
                project_versions_db.pop('GomeKu', None)
            else:
                project_versions_db['GomeKu'] = original_versions
            save_project_versions()
            if original_project is None:
                projects_db.pop('GomeKu', None)
            else:
                projects_db['GomeKu'] = original_project
            save_projects()

    def test_project_version_create_persists_platform_specific_fields(self):
        from models.data import project_versions_db, projects_db, save_project_versions, save_projects

        original_versions = copy.deepcopy(project_versions_db.get('GomeKu'))
        original_project = copy.deepcopy(projects_db.get('GomeKu'))
        projects_db['GomeKu'] = original_project or {
            'name': 'GomeKu',
            'created_by': 'admin',
            'editors': ['admin'],
            'viewers': [],
        }
        project_versions_db['GomeKu'] = []
        try:
            with self.client.session_transaction() as sess:
                sess['user'] = 'admin'
            r = self.client.post('/admin/projects/GomeKu/versions/create', json={
                'channel': 'dev',
                'stage': 'dev',
                'platform': 'android',
                'version_name': '3.1.0',
                'version_code': '310',
                'apk_path': 'android/GameKu_3.1.0.apk',
                'distribution_method': 'enterprise',
                'package_name': 'com.gameku.app',
                'min_sdk': '24',
            })
            data = r.get_json()
            self.assertEqual(r.status_code, 200)
            self.assertEqual(data['version']['distribution_method'], 'enterprise')
            self.assertEqual(data['version']['package_name'], 'com.gameku.app')
            self.assertEqual(data['version']['min_sdk'], '24')
            self.assertEqual(data['version']['bundle_id'], '')
            self.assertEqual(data['version']['min_ios_version'], '')
        finally:
            if original_versions is None:
                project_versions_db.pop('GomeKu', None)
            else:
                project_versions_db['GomeKu'] = original_versions
            save_project_versions()
            if original_project is None:
                projects_db.pop('GomeKu', None)
            else:
                projects_db['GomeKu'] = original_project
            save_projects()

    def test_project_version_create_rejects_mismatched_ios_extension(self):
        from models.data import project_versions_db, projects_db, save_project_versions, save_projects

        original_versions = copy.deepcopy(project_versions_db.get('GomeKu'))
        original_project = copy.deepcopy(projects_db.get('GomeKu'))
        projects_db['GomeKu'] = original_project or {
            'name': 'GomeKu',
            'created_by': 'admin',
            'editors': ['admin'],
            'viewers': [],
        }
        project_versions_db['GomeKu'] = []
        try:
            with self.client.session_transaction() as sess:
                sess['user'] = 'admin'
            r = self.client.post('/admin/projects/GomeKu/versions/create', json={
                'channel': 'dev',
                'stage': 'dev',
                'platform': 'ios',
                'version_name': '3.2.0',
                'version_code': '320',
                'apk_path': 'ios/GameKu_3.2.0.apk',
                'bundle_id': 'com.gameku.ios',
                'min_ios_version': '16.0',
            })
            data = r.get_json()
            self.assertEqual(r.status_code, 400)
            self.assertIn('.ipa', data['error'])
        finally:
            if original_versions is None:
                project_versions_db.pop('GomeKu', None)
            else:
                project_versions_db['GomeKu'] = original_versions
            save_project_versions()
            if original_project is None:
                projects_db.pop('GomeKu', None)
            else:
                projects_db['GomeKu'] = original_project
            save_projects()


if __name__ == '__main__':
    unittest.main()
