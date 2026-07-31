"""Version module — shared constants."""

from __future__ import annotations


VERSION_STAGES = [("dev", "开发"), ("test", "测试"), ("production", "线上")]


VERSION_STATUSES = [("draft", "草稿"), ("testing", "测试中"), ("active", "有效"), ("disabled", "失效"), ("archived", "归档")]


VERSION_STATUS_MAP = dict(VERSION_STATUSES)


STAGE_LABEL_MAP = dict(VERSION_STAGES)


VC_PIPELINE_PROTECTED_KEYS = {
    "pipeline",
    "pipeline_template",
    "jenkins_instance_id",
    "jenkins_job_id",
    "jenkins_params",
    "resource_server_url",
    "catalog_file_name",
    "min_client_version",
    "rollout_percentage",
    "force_update",
    "is_revoked",
}

