# -*- coding: utf-8 -*-
"""Release order constants."""

from __future__ import annotations

from services.release.order_state_machine import PUBLISHABLE_STATUSES, TERMINAL_STATUSES

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
    "server_release_id",
    "linked_server_release_id",
    "server_artifact_id",
    "target_services",
    "min_server_version",
    "waive_server_release_check",
    "deploy_server_with_client",
    "rollback_with_server",
    "announcement_title",
    "announcement_body",
    "announcement_effective_at",
    "sync_announcement",
    "server_maintenance_message",
)
