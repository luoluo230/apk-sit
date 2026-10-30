# -*- coding: utf-8 -*-
"""Topology plane. Parts share this module so existing cross-calls stay valid."""
from pathlib import Path

from services.ops.namespace_loader import load_parts

_PARTS = [
    "_header.py",
    "daemon.py",
    "design_demo.py",
    "dispatch.py",
    "gameserver_1.py",
    "gameserver_2.py",
    "gameserver_3.py",
    "logs_1.py",
    "logs_2.py",
    "logs_3.py",
    "logs_4.py",
    "logs_5.py",
    "logs_6.py",
    "nodes_1.py",
    "nodes_2.py",
    "registry_crud_1.py",
    "registry_crud_2.py",
    "runtime_bindings.py",
]

load_parts(globals(), Path(__file__).resolve().parent / "topology", _PARTS)
