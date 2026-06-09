# -*- coding: utf-8 -*-

import unittest

from services.release.env_registry import (
    normalize_release_env_key,
    env_key_to_stage,
    env_key_to_gm_env,
    env_key_to_jenkins_env,
)


class ReleaseEnvRegistryTests(unittest.TestCase):
    def test_normalize_aliases(self):
        self.assertEqual(normalize_release_env_key("Development"), "development")
        self.assertEqual(normalize_release_env_key("prod"), "production")
        self.assertEqual(normalize_release_env_key("staging"), "staging")
        self.assertNotEqual(normalize_release_env_key("staging"), "testing")

    def test_four_table_mapping(self):
        self.assertEqual(env_key_to_stage("production"), "production")
        self.assertEqual(env_key_to_gm_env("production"), "prod")
        self.assertEqual(env_key_to_jenkins_env("staging"), "Staging")


if __name__ == "__main__":
    unittest.main()
