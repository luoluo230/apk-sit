# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from unittest.mock import patch

from data._store import load_document
from data.users import USERS_FILE, save_users, users_db


class UsersDataTests(unittest.TestCase):
    def setUp(self):
        self._original_users = dict(users_db)

    def tearDown(self):
        users_db.clear()
        users_db.update(self._original_users)

    def test_users_db_roundtrip(self):
        username = '__test_roundtrip_user__'
        payload = {
            'password': 'deadbeef',
            'role': 'user',
            'created_at': '2026-06-21T00:00:00',
            'email': 'roundtrip@example.com',
            'last_login': None,
        }
        with tempfile.TemporaryDirectory() as tmp:
            test_file = os.path.join(tmp, 'users.json')
            env_patch = patch.dict(os.environ, {'USE_SQLITE': 'false'})
            sqlite_patch = patch('config.Config.USE_SQLITE', False)
            path_patch_users = patch('data.users.USERS_FILE', test_file)
            with env_patch, sqlite_patch, path_patch_users:
                users_db[username] = dict(payload)
                save_users()
                loaded = load_document(test_file, {})
            self.assertIn(username, loaded)
            self.assertEqual(loaded[username]['role'], payload['role'])
            self.assertEqual(loaded[username]['email'], payload['email'])


if __name__ == '__main__':
    unittest.main()
