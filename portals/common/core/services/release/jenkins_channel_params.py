# -*- coding: utf-8 -*-
"""Single contract for Jenkins channel identity fields (P3-03 Wave B).

- VERSION_CHANNEL_ID: catalog channel id (numeric or slug id)
- CHANNEL: Jenkins historical channel id (same as catalog id for Portal triggers)
- RELEASE_CHANNEL: OSS / remote path slug from normalize_release_channel
"""

from __future__ import annotations

from typing import Any, Dict

from services.commercial_release_plan import normalize_release_channel


def resolve_jenkins_channel_params(channel_id: str) -> Dict[str, str]:
    cid = str(channel_id or "").strip()
    if not cid:
        raise ValueError("渠道不能为空")
    slug = normalize_release_channel(cid)
    return {
        "VERSION_CHANNEL_ID": cid,
        "CHANNEL": cid,
        "RELEASE_CHANNEL": slug,
    }


def apply_jenkins_channel_params(params: Dict[str, Any], channel_id: str) -> Dict[str, Any]:
    """Mutate and return Jenkins params with the canonical channel triple."""
    triple = resolve_jenkins_channel_params(channel_id)
    out = params if isinstance(params, dict) else {}
    out["VERSION_CHANNEL_ID"] = triple["VERSION_CHANNEL_ID"]
    out["CHANNEL"] = triple["CHANNEL"]
    out["RELEASE_CHANNEL"] = triple["RELEASE_CHANNEL"]
    return out
