# -*- coding: utf-8 -*-
"""Runtime plane. Parts share this module so existing cross-calls stay valid."""
from pathlib import Path

from services.ops.namespace_loader import load_parts

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

load_parts(globals(), Path(__file__).resolve().parent / "runtime_parts", _PARTS)
