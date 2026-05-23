"""Settings service layer."""

from __future__ import annotations

from typing import Any, Dict, Iterable, Tuple

from repositories.admin import settings_repo
from services.admin.envelope import ok


def save_settings(data: Dict[str, Any], setting_keys: Iterable[tuple], username: str) -> Tuple[Dict[str, Any], int]:
    for key, _label, vtype, _default, desc in setting_keys:
        if key not in data:
            continue
        val = data[key]
        if vtype == "boolean":
            val = "true" if str(val).lower() in ("true", "1", "yes") else "false"
        settings_repo.set_value(key, str(val).strip() if val else "", vtype, desc, username)
    settings_repo.audit("system_settings_update", "")
    return ok({}, legacy={"success": True}), 200
