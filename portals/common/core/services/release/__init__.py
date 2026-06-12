# -*- coding: utf-8 -*-
"""Unified release platform: EnvRegistry, ReleaseScope, ReleaseBundle."""

from services.release.env_registry import (
    normalize_release_env_key,
    env_key_to_stage,
    env_key_to_gm_env,
    env_key_to_jenkins_env,
    stage_to_env_key,
)
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.scope_resolver import (
    resolve_scope,
    resolve_topology_id,
    resolve_topology_binding_for_scope,
    resolve_network_profile,
)
from services.release.release_context import resolve_release_context

__all__ = [
    "normalize_release_env_key",
    "env_key_to_stage",
    "env_key_to_gm_env",
    "env_key_to_jenkins_env",
    "stage_to_env_key",
    "resolve_scope",
    "resolve_topology_id",
    "resolve_topology_binding_for_scope",
    "resolve_network_profile",
    "build_scope_id",
    "project_slug",
    "resolve_channel_id",
    "resolve_release_context",
]
