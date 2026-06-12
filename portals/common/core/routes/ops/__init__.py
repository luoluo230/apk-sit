# -*- coding: utf-8 -*-
"""Ops platform blueprint (modular)."""
from flask import Blueprint

bp = Blueprint("gm_legacy", __name__)

# Load shared helpers before route modules (avoid partial import NameError)
import services.ops.helpers  # noqa: F401, E402

from routes.ops import pages  # noqa: F401, E402
from routes.ops import overview  # noqa: F401, E402
from routes.ops import cluster  # noqa: F401, E402
from routes.ops import agents  # noqa: F401, E402
import routes.ops.services as _svc_routes  # noqa: F401, E402  # avoid name collision with top-level services package
from routes.ops import topology  # noqa: F401, E402
from routes.ops import runtime  # noqa: F401, E402
from routes.ops import actions  # noqa: F401, E402
from routes.ops import business_test  # noqa: F401, E402
