# -*- coding: utf-8 -*-
"""Wire private symbols across split ops modules after import. Plan P1-01."""

from __future__ import annotations

import importlib
from types import ModuleType

MODULES = (
    "diagnostics",
    "topology_contracts",
    "cluster_importer",
    "topology_registry",
    "agent_registry",
    "runtime_orchestrator",
)


def _collect(module: ModuleType) -> dict[str, object]:
    out: dict[str, object] = {}
    for k in dir(module):
        if k.startswith("__"):
            continue
        if k.startswith("_") or (k.isupper() and k.replace("_", "").isalnum()):
            out[k] = getattr(module, k)
    return out


def wire_all() -> None:
    loaded = [importlib.import_module(f"services.ops.{name}") for name in MODULES]
    merged: dict[str, object] = {}
    for mod in loaded:
        merged.update(_collect(mod))
    for mod in loaded:
        for key, value in merged.items():
            mod.__dict__.setdefault(key, value)


def wire_module(name: str) -> None:
    mod = importlib.import_module(f"services.ops.{name}")
    merged: dict[str, object] = {}
    for module_name in MODULES:
        merged.update(_collect(importlib.import_module(f"services.ops.{module_name}")))
    for key, value in merged.items():
        mod.__dict__.setdefault(key, value)
