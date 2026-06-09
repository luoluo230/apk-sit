# -*- coding: utf-8 -*-
"""Route dependency injection: all ops helpers including underscore-prefixed."""
from __future__ import annotations

import services.ops.helpers as _helpers
import services.ops.storage as _storage

for _mod in (_helpers, _storage):
    for _name, _val in vars(_mod).items():
        if not _name.startswith("__"):
            globals()[_name] = _val

del _mod, _name, _val, _helpers, _storage
