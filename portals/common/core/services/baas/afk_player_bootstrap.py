# -*- coding: utf-8 -*-
"""Compatibility import. Implementation lives in services.baas.afk."""
from services.baas.afk.afk_player_bootstrap import *  # noqa: F401,F403
from services.baas.afk import afk_player_bootstrap as _impl
import sys
sys.modules[__name__] = _impl
