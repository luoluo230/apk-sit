# -*- coding: utf-8 -*-
"""P1: extract order_crud, order_build_sync, order_publish_flow from release_order_service."""

from __future__ import annotations

import os
import textwrap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
SRC = os.path.join(ROOT, "services", "release", "release_order_service.py")

HEADER = textwrap.dedent(
    '''
    # -*- coding: utf-8 -*-
    """Release order submodule."""

    from __future__ import annotations

    import json
    import os
    import uuid
    from datetime import datetime
    from typing import Any, Dict, List, Optional, Tuple

    from models.data import get_channel_by_id, get_channels_for_project,
    from data.delivery_scope import get_channels_for_env, get_platform_defs_for_env, is_channel_allowed_for_env
    from data.platforms import get_platform_defs_for_project, is_platform_enabled_for_project, is_valid_platform_id
    from models.db import _db_lock, _get_conn, get_cursor, init_db
    from services.release.bundle_service import find_active_bundle, list_publishable_bundles, run_scope_precheck
    from services.release.env_registry import list_project_env_keys, normalize_release_env_key, project_env_label
    from services.release.scope_ids import build_scope_id, project_slug, resolve_channel_id
    from services.release.scope_resolver import resolve_network_profile, resolve_scope, resolve_topology_binding_for_scope
    from services.release.topology_binding_service import resolve_topology_binding, upsert_topology_binding
    from services.release.storage import find_manifest
    from services.release.order_constants import EDITABLE_PLAN_FIELDS, PUBLISHABLE_STATUSES, TERMINAL_STATUSES
    from services.release.order_diagnostics import _build_pipeline_snapshot, _pipeline_build_ready, summarize_order_diagnostic_issues
    from services.release.order_helpers import (
        _artifact_rows,
        _bundle_id,
        _channel_name,
        _decode,
        _event,
        _find_version,
        _json,
        _now_iso,
        _order_id,
    )

    '''
).lstrip("\n")


def _lazy(name: str) -> str:
    return textwrap.dedent(
        f'''
        def _{name}():
            import services.release.{name} as mod
            return mod
        '''
    )


def main() -> int:
    with open(SRC, encoding="utf-8") as f:
        lines = f.readlines()

    # 1-based inclusive slices on current file
    crud_parts = [lines[36:423], lines[751:766], lines[1427:1479]]
    build_parts = [lines[200:300], lines[424:962]]
    publish_parts = [lines[964:1426]]

    crud_path = os.path.join(ROOT, "services", "release", "order_crud.py")
    with open(crud_path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write(_lazy("order_build_sync"))
        for part in crud_parts:
            f.writelines(part)

    build_path = os.path.join(ROOT, "services", "release", "order_build_sync.py")
    with open(build_path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write(_lazy("order_crud"))
        f.write(_lazy("order_publish_flow"))
        for part in build_parts:
            f.writelines(part)

    publish_path = os.path.join(ROOT, "services", "release", "order_publish_flow.py")
    with open(publish_path, "w", encoding="utf-8") as f:
        f.write(HEADER)
        f.write(_lazy("order_crud"))
        for part in publish_parts:
            f.writelines(part)

    facade = '''# -*- coding: utf-8 -*-
"""Release order facade — re-exports split modules for backward compatibility."""

from services.release.order_crud import *  # noqa: F401,F403
from services.release.order_build_sync import *  # noqa: F401,F403
from services.release.order_publish_flow import *  # noqa: F401,F403
from services.release.channel_journey_bff import (  # noqa: F401
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
    with open(SRC, "w", encoding="utf-8") as f:
        f.write(facade)

    print("Wrote", crud_path, build_path, publish_path, SRC)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())