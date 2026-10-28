# -*- coding: utf-8 -*-
"""Compatibility import. Implementation lives in services.baas.afk."""
from services.baas.afk.afk_retention_hooks import *  # noqa: F401,F403
from services.baas.afk import afk_retention_hooks as _impl
import sys
sys.modules[__name__] = _impl
