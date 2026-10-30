# -*- coding: utf-8 -*-
"""Load split source files into one module namespace.

Topology and runtime call each other by bare name. They stay one namespace
per plane so those calls, and patches on the facade, keep working.
"""

from __future__ import annotations

from pathlib import Path


def load_parts(target_globals: dict, folder: Path, parts: list[str]) -> None:
    for name in parts:
        path = folder / name
        code = path.read_text(encoding="utf-8")
        exec(compile(code, str(path), "exec"), target_globals)
