# -*- coding: utf-8 -*-
"""End-to-end release platform verification."""

from __future__ import annotations

import os
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)

from models.data import projects_db, project_versions_db
from services.release.storage import find_manifest, load_scopes
from services.release.release_context import resolve_release_context


def main() -> int:
    pid = "GomeKu"
    print("=== E2E RELEASE PLATFORM VERIFICATION ===\n")
    errors = []

    # 1. Credentials
    p = projects_db.get(pid, {})
    gid = p.get("game_id", "")
    gk = p.get("game_key", "")
    if gid and gk:
        print("PASS 1. Credentials: game_id=%s... game_key=%s..." % (gid[:24], gk[:8]))
    else:
        msg = "FAIL 1. No game credentials in projects_db"
        print(msg)
        errors.append(msg)

    # 2. Manifest
    m = find_manifest(pid)
    if m:
        print("PASS 2. Manifest: slug=%s channels=%d" % (m.get("project_slug"), len(m.get("channels", []))))
        m_gid = m.get("game_id", "")
        if m_gid == gid:
            print("     Manifest credentials match projects_db: YES")
        else:
            msg = "FAIL 2b. Manifest game_id mismatch: %s vs %s" % (m_gid, gid)
            print(msg)
            errors.append(msg)
    else:
        msg = "FAIL 2. No manifest"
        print(msg)
        errors.append(msg)

    # 3. Scopes
    scopes = [s for s in load_scopes() if s.get("project_id") == pid]
    print("PASS 3. Scopes: %d total" % len(scopes))
    for s in scopes:
        print("     %s status=%s" % (s["scope_id"], s.get("status")))

    if len(scopes) < 8:
        msg = "WARN 3b. Expected 8 scopes (4 env x 2 channels), got %d" % len(scopes)
        print(msg)

    # 4. Version rows
    versions = project_versions_db.get(pid, [])
    with_scope = [v for v in versions if v.get("scope_id")]
    without = len(versions) - len(with_scope)
    if without == 0:
        print("PASS 4. Versions: %d total, all have scope_id" % len(versions))
    else:
        msg = "WARN 4. Versions: %d total, %d missing scope_id" % (len(versions), without)
        print(msg)

    # 5. Release context resolution
    print("\n--- Release Context Resolution ---")
    for env in ["development", "production"]:
        for ch in ["1001", "1002"]:
            ctx = resolve_release_context(pid, env, ch)
            prof = ctx.get("network_profile", {})
            gw = prof.get("gateway_ws", "")
            src = ctx.get("profile_source", "")
            sid = ctx.get("scope_id", "")
            bid = ctx.get("active_bundle_id", "")
            gw_display = gw[:50] if gw else "NONE"
            status = "PASS" if sid else "FAIL"
            print("%s 5. [%s:%s] scope=%s src=%s gateway=%s bundle=%s" % (
                status, env, ch, sid, src, gw_display, bid or "NONE"
            ))
            if not sid:
                errors.append("FAIL context for %s:%s" % (env, ch))

    # 6. Simulate bootstrap auth lookup
    print("\n--- Bootstrap Auth Lookup ---")
    from routes.gm_ops import _find_project_by_game_credentials
    found_pid = _find_project_by_game_credentials(gid, gk)
    if found_pid == pid:
        print("PASS 6. _find_project_by_game_credentials(%s, ***) -> %s" % (gid[:16], found_pid))
    else:
        msg = "FAIL 6. credential lookup returned %s" % found_pid
        print(msg)
        errors.append(msg)

    # 7. Channel options from catalog
    print("\n--- Channel Options ---")
    from routes.gm_ops import _project_envs_and_channels
    ec = _project_envs_and_channels(pid)
    print("     envs=%s" % ec["envs"])
    print("     channels=%s" % ec["channels"])
    if "1001" in ec["channels"]:
        print("PASS 7. Manifest channel 1001 in channel list")
    else:
        msg = "FAIL 7. Channel 1001 not in list: %s" % ec["channels"]
        print(msg)
        errors.append(msg)

    print("\n=== SUMMARY ===")
    if errors:
        print("ERRORS: %d" % len(errors))
        for e in errors:
            print("  - %s" % e)
        return 1
    else:
        print("ALL CHECKS PASSED")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
