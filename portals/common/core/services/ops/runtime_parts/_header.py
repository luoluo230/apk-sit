"""Runtime start/stop orchestration and probes."""
from __future__ import annotations
from services.ops import shared_bootstrap as _boot
globals().update({k: getattr(_boot, k) for k in dir(_boot) if not k.startswith("__")})
from services.ops.topology_service import _normalize_env_key, _runtime_default_topology_id
