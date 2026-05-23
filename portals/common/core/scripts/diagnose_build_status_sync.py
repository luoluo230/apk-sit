#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Diagnose build status source drift for version workflow.

Checks the latest build records and compares:
1) local builds dir visibility
2) Jenkins API status

This script is read-only and does not mutate data.
"""

import json
import os
import sqlite3
import sys


ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from config import DATA_DIR  # noqa: E402
from services import jenkins_manager as jm  # noqa: E402
from services import jenkins as jenkins_svc  # noqa: E402


def _load_records(limit=30):
    db_path = os.path.join(DATA_DIR, "apk_site.db")
    conn = sqlite3.connect(db_path)
    row = conn.execute(
        "SELECT payload FROM json_documents WHERE document_key=?",
        ("data/build_version_records.json",),
    ).fetchone()
    if not row:
        return []
    items = json.loads(row[0])
    if not isinstance(items, list):
        return []
    return items[-limit:]


def main():
    records = _load_records(40)
    if not records:
        print("No build records found.")
        return

    print("build_number\tinstance_id\tlocal_build_xml\tapi_status\tapi_building")
    for rec in records:
        bn = int(rec.get("build_number") or 0)
        iid = str(rec.get("instance_id") or "").strip()
        iurl = jm.get_jenkins_url_for_instance(instance_id=iid) if iid else None
        bdir = jm.get_builds_dir_for_instance(instance_id=iid) if iid else None
        bxml = os.path.join(bdir, str(bn), "build.xml") if bdir else ""
        local_ok = os.path.isfile(bxml)
        st = jenkins_svc.get_build_status(
            bn,
            base_url=iurl,
            builds_dir=bdir,
            instance_id=iid,
        )
        print(
            f"{bn}\t{iid}\t{str(local_ok)}\t{st.get('status','')}\t{str(bool(st.get('building')))}"
        )


if __name__ == "__main__":
    main()
