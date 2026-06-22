# -*- coding: utf-8 -*-

import os
import tempfile
import unittest
from unittest.mock import patch

from data._store import Storage, load_document
from data.repositories.user_repository import UserRepository


class UserRepositoryTests(unittest.TestCase):
    def test_create_find_update_delete_roundtrip(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_file = os.path.join(tmp, 'users.json')
            storage = Storage(test_file, default={})
            repo = UserRepository(storage=storage)

            created = repo.create('alice', {'password': 'hash', 'role': 'user', 'email': 'a@example.com'})
            self.assertEqual(created['role'], 'user')

            found = repo.find('alice')
            self.assertIsNotNone(found)
            self.assertEqual(found['email'], 'a@example.com')

            updated = repo.update('alice', {'role': 'admin'})
            self.assertEqual(updated['role'], 'admin')

            self.assertTrue(repo.delete('alice'))
            self.assertIsNone(repo.find('alice'))

    def test_persist_via_storage_file(self):
        with tempfile.TemporaryDirectory() as tmp:
            test_file = os.path.join(tmp, 'users.json')
            env_patch = patch.dict(os.environ, {'USE_SQLITE': 'false'})
            sqlite_patch = patch('config.Config.USE_SQLITE', False)
            with env_patch, sqlite_patch:
                repo = UserRepository(storage=Storage(test_file, default={}))
                repo.create('bob', {'password': 'x', 'role': 'user'})
                loaded = load_document(test_file, {})
            self.assertIn('bob', loaded)
            self.assertEqual(loaded['bob']['role'], 'user')

    def test_sync_module_cache(self):
        repo = UserRepository(storage=Storage(os.path.join(tempfile.gettempdir(), 'unused_users.json'), default={}))
        repo.create('cache_user', {'password': 'x', 'role': 'viewer'})
        cache = {}
        repo.sync_module_cache(cache)
        self.assertIn('cache_user', cache)
        repo.delete('cache_user')


if __name__ == '__main__':
    unittest.main()
