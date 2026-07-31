# -*- coding: utf-8 -*-
"""Multi-process registry read-after-write (P0-02 Step 2)."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import tempfile
import textwrap
import unittest
import uuid

_CORE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)


class TestMultiWorkerRegistry(unittest.TestCase):
    def test_process_a_write_process_b_read(self):
        slug = f"mw{uuid.uuid4().hex[:8]}"
        project_id = slug.title()
        marker_file = os.path.join(tempfile.gettempdir(), f"registry_mw_{slug}.json")
        if os.path.isfile(marker_file):
            os.remove(marker_file)

        writer = textwrap.dedent(
            f"""
            import json, os, sys
            sys.path.insert(0, {repr(_CORE)})
            os.environ["USE_SQLITE"] = "true"
            from models.db import init_db, reset_db_connection
            from repositories.registry import accessors
            reset_db_connection(close_all=True)
            init_db()
            accessors.save_project({repr(project_id)}, {{
                "project_id": {repr(project_id)},
                "slug": {repr(slug)},
                "name": "MW Test",
                "platforms": ["android"],
            }})
            with open({repr(marker_file)}, "w", encoding="utf-8") as fp:
                json.dump({{"project_id": {repr(project_id)}, "slug": {repr(slug)}}}, fp)
            """
        )
        reader = textwrap.dedent(
            f"""
            import json, os, sys, time
            sys.path.insert(0, {repr(_CORE)})
            os.environ["USE_SQLITE"] = "true"
            from models.db import init_db, reset_db_connection
            from repositories.registry import accessors
            deadline = time.time() + 30
            meta = None
            while time.time() < deadline:
                if os.path.isfile({repr(marker_file)}):
                    with open({repr(marker_file)}, "r", encoding="utf-8") as fp:
                        meta = json.load(fp)
                    break
                time.sleep(0.2)
            if not meta:
                raise SystemExit("marker missing")
            reset_db_connection(close_all=True)
            init_db()
            row = accessors.get_project(meta["project_id"])
            if not row or row.get("slug") != meta["slug"]:
                raise SystemExit("read failed")
            print("OK")
            """
        )
        wproc = subprocess.Popen([sys.executable, "-c", writer], cwd=_CORE)
        rproc = subprocess.Popen([sys.executable, "-c", reader], cwd=_CORE, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        wcode = wproc.wait(timeout=60)
        rout, rerr = rproc.communicate(timeout=60)
        self.assertEqual(wcode, 0, msg=rerr.decode())
        self.assertEqual(rproc.returncode, 0, msg=rerr.decode())
        self.assertIn(b"OK", rout)


if __name__ == "__main__":
    unittest.main()
