# -*- coding: utf-8 -*-

import unittest

from services.release.scope_ids import build_scope_id, project_slug


class ScopeResolverTests(unittest.TestCase):
    def test_scope_id_generation(self):
        self.assertEqual(build_scope_id("gomeku", "production", "1001"), "gomeku:production:1001")

    def test_project_slug(self):
        self.assertEqual(project_slug("GomeKu"), "gomeku")


if __name__ == "__main__":
    unittest.main()
