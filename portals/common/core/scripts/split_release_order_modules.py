# -*- coding: utf-8 -*-
"""One-off helper: extract release_order_service submodules (run from portals/common/core)."""

from __future__ import annotations

import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "services", "release", "release_order_service.py")

COMMON_HEADER = '''# -*- coding: utf-8 -*-
"""Release order submodule (extracted from release_order_service)."""

from __future__ import annotations

import json
import os
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from models.data import get_channel_by_id, get_channels_for_project
from data.delivery_scope import get_channels_for_env, get_platform_defs_for_env, is_channel_allowed_for_env
from data.platforms import get_platform_defs_for_project, is_platform_enabled_for_project, is_valid_platform_id
from models.db import _db_lock, _get_conn, get_cursor, init_db
from services.release.bundle_service import find_active_bundle, list_publishable_bundles, run_scope_precheck
from services.release.env_registry import list_project_env_keys, normalize_release_env_key, project_env_label
from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
from services.release.scope_resolver import resolve_network_profile, resolve_scope, resolve_topology_binding_for_scope
from services.release.storage import find_manifest

from services.release.order_constants import EDITABLE_PLAN_FIELDS, PUBLISHABLE_STATUSES, TERMINAL_STATUSES
from repositories.registry.accessors import get_project, has_project, list_projects, save_project, list_channels, list_project_versions, save_project_versions
from services.release.order_helpers import (
    _artifact_rows,
    _channel_name,
    _decode,
    _event,
    _find_version,
    _json,
    _now_iso,
    _order_from_row,
    _order_id,
    _bundle_id,
)

'''


def main() -> int:
    with open(SRC, encoding="utf-8") as handle:
        lines = handle.readlines()

    # 1-based line ranges inclusive
    diagnostics = lines[204:611]  # 205-611
    journey = lines[1980:2592]  # 1981-2592

    diag_path = os.path.join(ROOT, "services", "release", "order_diagnostics.py")
    with open(diag_path, "w", encoding="utf-8") as handle:
        handle.write(COMMON_HEADER)
        handle.writelines(diagnostics)

    journey_header = COMMON_HEADER.replace(
        "from services.release.order_helpers import (",
        "from services.release.order_helpers import (\n    _find_version,",
    )
    journey_path = os.path.join(ROOT, "services", "release", "channel_journey_bff.py")
    with open(journey_path, "w", encoding="utf-8") as handle:
        handle.write(journey_header)
        handle.writelines(journey)

    # Remove extracted blocks from bottom to top
    new_lines = lines[:204] + lines[611:1980] + lines[2592:]
    footer = '''

# --- Extracted modules (re-export for backward compatibility) ---
from services.release.order_diagnostics import summarize_order_diagnostic_issues  # noqa: E402,F401
from services.release.channel_journey_bff import (  # noqa: E402
    BUILD_JOURNEY_STEPS,
    RELEASE_JOURNEY_STEPS,
    _channel_entry_urls,
    _delivery_lines_for_env,
    _enrich_state_from_version_id,
    _jenkins_progress_pct,
    _lines_for_channel,
    _platform_state_for_journey,
    _resolve_build_current_step,
    _resolve_release_current_step,
    _version_id_for_delivery_line,
    _versions_for_channel_platform,
    environment_detail,
    project_overview,
    resolve_channel_build_journey,
    resolve_channel_journey_entries,
    resolve_channel_release_journey,
)
'''
    with open(SRC, "w", encoding="utf-8") as handle:
        handle.writelines(new_lines)
        handle.write(footer)
    print("Wrote", diag_path, journey_path, "and trimmed", SRC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())