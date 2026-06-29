#!/usr/bin/env python3
"""Re-trigger Jenkins build for an existing release order and poll until done."""

from __future__ import annotations

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from config import load_dotenv

load_dotenv()

from app_new import app
from models.db import init_db
from services import jenkins as jenkins_svc
from services import jenkins_manager as jm
from services.release.release_order_service import request_build

PROJECT_ID = "GomeKu"
ORDER_ID = "ro-20260625141926-76e9c8"
USERNAME = "admin"
INSTANCE_ID = "10477171"


def main() -> int:
    init_db()
    with app.test_request_context():
        from flask import session

        session["user"] = USERNAME
        order = request_build(PROJECT_ID, ORDER_ID, USERNAME)
    build_no = int((order.get("payload") or {}).get("build_job_id") or 0)
    print(f"BUILD {build_no}", flush=True)
    base = jm.get_jenkins_url_for_instance(instance_id=INSTANCE_ID)
    bdir = jm.get_builds_dir_for_instance(instance_id=INSTANCE_ID)
    while True:
        st = jenkins_svc.get_build_status(build_no, base_url=base, builds_dir=bdir, instance_id=INSTANCE_ID)
        print(f"STATUS {st}", flush=True)
        if st in ("SUCCESS", "FAILURE", "ABORTED", "UNSTABLE"):
            return 0 if st == "SUCCESS" else 1
        time.sleep(30)


if __name__ == "__main__":
    raise SystemExit(main())
