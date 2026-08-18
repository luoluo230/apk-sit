# -*- coding: utf-8 -*-
"""ReleaseOrder formal state machine — explicit allowed transitions."""

from __future__ import annotations

from typing import Dict, List, Optional, Sequence, Set

# All known release-order statuses (superset for validation messages).
ALL_STATUSES: Sequence[str] = (
    "draft",
    "building",
    "build_failed",
    "artifacts_ready",
    "prechecking",
    "precheck_failed",
    "ready",
    "awaiting_approval",
    "approved",
    "publishing",
    "publish_failed",
    "published",
    "verifying",
    "verify_failed",
    "verified",
    "rolled_back",
    "cancelled",
)

TERMINAL_STATUSES: Set[str] = {"verified", "rolled_back", "cancelled"}

PUBLISHABLE_STATUSES: Set[str] = {"ready", "approved"}

# Explicit transition table: current -> allowed targets
_ALLOWED_TRANSITIONS: Dict[str, Set[str]] = {
    "draft": {"building", "artifacts_ready", "cancelled"},
    "building": {"artifacts_ready", "build_failed", "cancelled"},
    "build_failed": {"building", "draft", "cancelled", "artifacts_ready"},
    "artifacts_ready": {"prechecking", "building", "cancelled", "draft"},
    "prechecking": {"ready", "precheck_failed", "awaiting_approval"},
    "precheck_failed": {"prechecking", "building", "cancelled", "draft", "artifacts_ready"},
    "ready": {"publishing", "prechecking", "cancelled", "awaiting_approval"},
    "awaiting_approval": {"approved", "cancelled"},
    "approved": {"publishing", "prechecking", "cancelled"},
    "publishing": {"published", "publish_failed"},
    "publish_failed": {"publishing", "prechecking", "cancelled", "ready", "approved"},
    "published": {"verifying", "rolled_back", "published"},
    "verifying": {"verified", "verify_failed"},
    "verify_failed": {"verifying", "rolled_back"},
    "verified": {"rolled_back", "published"},
    "rolled_back": {"published"},
    "cancelled": set(),
}


def normalize_status(status: str) -> str:
    return str(status or "draft").strip().lower() or "draft"


def allowed_targets(from_status: str) -> Set[str]:
    current = normalize_status(from_status)
    return set(_ALLOWED_TRANSITIONS.get(current, set()))


def can_transition(from_status: str, to_status: str) -> bool:
    current = normalize_status(from_status)
    target = normalize_status(to_status)
    if current == target:
        return True
    return target in _ALLOWED_TRANSITIONS.get(current, set())


def validate_transition(from_status: str, to_status: str) -> List[str]:
    """Return violation messages; empty list means allowed."""
    current = normalize_status(from_status)
    target = normalize_status(to_status)
    if current == target:
        return []
    allowed = _ALLOWED_TRANSITIONS.get(current)
    if allowed is None:
        return [f"unknown current status: {current!r}"]
    if target not in allowed:
        opts = ", ".join(sorted(allowed)) or "(none)"
        return [f"不允许从 {current} 转到 {target}（允许: {opts}）"]
    return []


def assert_transition(from_status: str, to_status: str) -> None:
    errors = validate_transition(from_status, to_status)
    if errors:
        raise ValueError(errors[0])


def is_terminal(status: str) -> bool:
    return normalize_status(status) in TERMINAL_STATUSES


def transition_matrix() -> Dict[str, List[str]]:
    """Export table for docs/tests."""
    return {k: sorted(v) for k, v in _ALLOWED_TRANSITIONS.items()}
