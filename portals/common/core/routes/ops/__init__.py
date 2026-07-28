# -*- coding: utf-8 -*-
"""Project-owned operations blueprint."""
from flask import Blueprint

bp = Blueprint("project_ops", __name__)

# Load shared ops symbols (submodules + facade auth/render) before route modules
from routes.ops import deps as _ops_deps  # noqa: F401, E402
from services.ops import cross_bind

cross_bind.wire_all()

from routes.ops import pages  # noqa: F401, E402
from routes.ops import overview  # noqa: F401, E402
from routes.ops import cluster  # noqa: F401, E402
from routes.ops import agents  # noqa: F401, E402
import routes.ops.services as _svc_routes  # noqa: F401, E402  # avoid name collision with top-level services package
from routes.ops import topology  # noqa: F401, E402
from routes.ops import runtime  # noqa: F401, E402
from routes.ops import actions  # noqa: F401, E402
from routes.ops import business_test  # noqa: F401, E402
