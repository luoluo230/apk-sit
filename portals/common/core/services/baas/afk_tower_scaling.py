# -*- coding: utf-8 -*-
"""Compatibility import. Implementation lives in services.baas.afk."""
from services.baas.afk.afk_tower_scaling import *  # noqa: F401,F403
from services.baas.afk import afk_tower_scaling as _impl
import sys
sys.modules[__name__] = _impl
