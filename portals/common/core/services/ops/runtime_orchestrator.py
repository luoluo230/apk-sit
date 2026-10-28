# -*- coding: utf-8 -*-
"""Facade. Grouped sources share one namespace so existing cross-calls stay valid."""
from pathlib import Path

_PARTS = [
    "_header.py",
    "lifecycle_1.py",
    "lifecycle_2.py",
    "lifecycle_3.py",
    "probes_1.py",
    "probes_2.py",
    "probes_3.py",
    "support_1.py",
    "support_2.py",
    "support_3.py",
]

def _load_parts():
    folder = Path(__file__).resolve().parent / "runtime_parts"
    for name in _PARTS:
        path = folder / name
        code = path.read_text(encoding="utf-8")
        exec(compile(code, str(path), "exec"), globals())

_load_parts()
