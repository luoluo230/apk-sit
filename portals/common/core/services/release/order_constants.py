# -*- coding: utf-8 -*-
"""Release order constants."""

from __future__ import annotations

TERMINAL_STATUSES = {"verified", "rolled_back", "cancelled"}
PUBLISHABLE_STATUSES = {"ready", "approved"}
EDITABLE_PLAN_FIELDS = (
    "owner",
    "release_window",
    "change_order",
    "related_requirements",
    "related_tasks",
    "release_description",
    "jenkins_instance_id",
    "jenkins_job",
    "jenkins_params",
    "target_topology_id",
    "release_strategy",
    "release_reason_type",
    "gray_strategy",
    "gray_ratio",
    "validation_items",
    "gray_duration",
    "gray_success_action",
    "target_audience",
    "validation_plan",
    "validation_task",
    "rollback_plan",
    "rollback_target",
    "rollback_condition",
    "rollback_method",
    "rollback_timeout_minutes",
)
