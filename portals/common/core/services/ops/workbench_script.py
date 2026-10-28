# -*- coding: utf-8 -*-
"""Assemble the topology workbench script from ordered parts."""

from pathlib import Path

_PARTS = Path(__file__).resolve().parents[2] / "static" / "ops_workbench"


def workbench_javascript() -> str:
    chunks = []
    for path in sorted(_PARTS.glob("part_*.js")):
        chunks.append(path.read_text(encoding="utf-8").rstrip())
    return "(function () {\n" + "\n".join(chunks) + "\n})();\n"
