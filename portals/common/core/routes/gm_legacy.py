# -*- coding: utf-8 -*-
"""Re-export modular Ops + legacy GM blueprint and helpers for backward compatibility."""
from __future__ import annotations

import json
import os
import subprocess

import routes.ops.deps as _ops_deps
from routes.ops import bp  # noqa: F401

globals().update({k: v for k, v in vars(_ops_deps).items() if not k.startswith("__")})

del _ops_deps
