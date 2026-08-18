# -*- coding: utf-8 -*-
"""Tests for ReleaseOrder state machine."""

from __future__ import annotations

import os
import sys
import unittest

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

from services.release.order_state_machine import (
    ALL_STATUSES,
    assert_transition,
    can_transition,
    transition_matrix,
    validate_transition,
)


class OrderStateMachineTests(unittest.TestCase):
    def test_publish_happy_path_transitions(self):
        path = [
            ("draft", "building"),
            ("building", "artifacts_ready"),
            ("artifacts_ready", "prechecking"),
            ("prechecking", "ready"),
            ("ready", "publishing"),
            ("publishing", "published"),
            ("published", "verifying"),
            ("verifying", "verified"),
        ]
        for src, dst in path:
            self.assertTrue(can_transition(src, dst), f"{src}->{dst}")

    def test_illegal_skip_precheck_blocked(self):
        self.assertFalse(can_transition("draft", "published"))
        errors = validate_transition("draft", "published")
        self.assertTrue(errors)

    def test_rollback_transitions(self):
        assert_transition("published", "rolled_back")
        assert_transition("rolled_back", "published")
        assert_transition("verified", "published")

    def test_build_failed_recovery(self):
        assert_transition("building", "build_failed")
        assert_transition("build_failed", "building")

    def test_assert_transition_raises(self):
        with self.assertRaises(ValueError):
            assert_transition("cancelled", "published")

    def test_transition_matrix_covers_all_statuses(self):
        matrix = transition_matrix()
        for status in ALL_STATUSES:
            self.assertIn(status, matrix)


if __name__ == "__main__":
    unittest.main()
