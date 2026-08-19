# -*- coding: utf-8 -*-
"""Tests for admin global search service."""

from __future__ import annotations

import unittest


class TestGlobalSearchService(unittest.TestCase):
    def test_empty_query_returns_empty_buckets(self):
        from services.admin.global_search_service import flatten_search_hits, search_admin_content

        results = search_admin_content("", "admin")
        self.assertEqual(results["projects"], [])
        self.assertEqual(flatten_search_hits(results), [])

    def test_flatten_respects_limit(self):
        from services.admin.global_search_service import flatten_search_hits

        results = {
            "projects": [{"id": "p1", "title": "A", "link": "/a", "category": "project"}],
            "release_orders": [{"id": "r1", "title": "B", "link": "/b", "category": "release_order"}],
            "versions": [],
            "docs": [],
            "tasks": [],
            "users": [],
        }
        hits = flatten_search_hits(results, limit=1)
        self.assertEqual(len(hits), 1)
        self.assertEqual(hits[0]["category"], "project")


if __name__ == "__main__":
    unittest.main()
