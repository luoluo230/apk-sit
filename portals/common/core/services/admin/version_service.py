"""Version API service — thin facade; logic in sibling modules."""

from __future__ import annotations

from services.admin.version_constants import (  # noqa: F401
    VERSION_STAGES,
    VERSION_STATUSES,
    VC_PIPELINE_PROTECTED_KEYS,
)
from services.admin.version_row_helpers import _resolve_runtime_compat_fields  # noqa: F401
from services.admin.version_pipeline_resolver import (  # noqa: F401
    _apply_project_build_defaults_to_pipeline,
    _merge_version_pipeline,
    _save_pipeline_template_to_meta,
    enrich_version_client_urls,
    resolve_effective_bootstrap_fields,
    resolve_effective_ios_signing,
    resolve_effective_jenkins,
    resolve_effective_pipeline,
)
from services.admin.version_group_repo import (  # noqa: F401
    _find_group_meta_index,
    _get_group_meta,
    _load_version_groups_meta,
    _version_matches_group_scope,
    _version_row_env_key,
    _version_row_platform,
    get_version_group_meta,
)
from services.admin.version_propagation import _propagate_pipeline_to_group_scope  # noqa: F401
from services.admin.version_group_service import (  # noqa: F401
    create_version_group,
    delete_version_group,
    list_version_groups,
    update_version_group,
    update_version_group_platform_config,
)
from services.admin.version_download_service import (  # noqa: F401
    get_apk_download_info,
    get_version_downloads,
    list_versions,
    project_download_stats,
)
from services.admin.version_runtime_service import (  # noqa: F401
    build_version_runtime_preview,
    get_version_effective_pipeline,
    get_version_runtime_preview,
)
from services.admin.version_crud_service import (  # noqa: F401
    _build_new_version_row,
    create_version,
    delete_version,
    update_version,
)

__all__ = [
    "VERSION_STAGES",
    "VERSION_STATUSES",
    "VC_PIPELINE_PROTECTED_KEYS",
    "_get_group_meta",
    "_load_version_groups_meta",
    "_find_group_meta_index",
    "_version_matches_group_scope",
    "_merge_version_pipeline",
    "_apply_project_build_defaults_to_pipeline",
    "_resolve_runtime_compat_fields",
    "_version_row_env_key",
    "_version_row_platform",
    "_propagate_pipeline_to_group_scope",
    "_save_pipeline_template_to_meta",
    "enrich_version_client_urls",
    "resolve_effective_bootstrap_fields",
    "resolve_effective_ios_signing",
    "resolve_effective_jenkins",
    "resolve_effective_pipeline",
    "get_version_group_meta",
    "list_version_groups",
    "create_version_group",
    "update_version_group",
    "delete_version_group",
    "update_version_group_platform_config",
    "project_download_stats",
    "list_versions",
    "get_version_effective_pipeline",
    "get_version_downloads",
    "build_version_runtime_preview",
    "get_version_runtime_preview",
    "get_apk_download_info",
    "create_version",
    "update_version",
    "delete_version",
    "_build_new_version_row",
]
