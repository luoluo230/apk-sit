# -*- coding: utf-8 -*-
"""Text encoding / mojibake helpers."""
from __future__ import annotations

from typing import Any, Dict

_REPLACEMENT = chr(0xFFFD)


def text_has_mojibake(text: str) -> bool:
    if not text:
        return False
    if _REPLACEMENT in text or "锟" in text:
        return True
    return False


def repair_legacy_node_text(item: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(item or {})
    for key in ("name", "label", "desc", "note"):
        val = str(out.get(key) or "")
        if text_has_mojibake(val):
            out[key] = val.replace(_REPLACEMENT, "")
    return out
