#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Live HTTP (urllib → localhost:5004) AFK stage-100 chain — no Flask test_client."""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

CREDS = CORE / "docs/evidence/baas-afk-live-e2e-credentials.json"
OUT = Path(__file__).resolve().parents[4] / "data/afk_shared/afk_live_http_stage100_report.json"


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=45) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": raw, "status": exc.code}


def stage_ids(limit: int = 100) -> list[str]:
    out: list[str] = []
    for ch in range(1, 11):
        for lv in range(1, 11):
            out.append(f"AFK_{ch:02d}_{lv:02d}")
            if len(out) >= limit:
                return out
    return out


def main() -> int:
    from services.baas.battle_antifraud import compute_replay_hash
    from services.baas.afk_formula_engine import team_power_from_defs, level_up_cost
    from services.baas.afk_config_loader import load_afk_bundle, hero_def_map

    portal = os.environ.get("BAAS_E2E_PORTAL", "http://127.0.0.1:5004").rstrip("/")
    creds = json.loads(CREDS.read_text(encoding="utf-8"))
    base = f"{portal}/api/baas/v1/{creds['service_id']}"
    api_h = {"X-Baas-Api-Key": creds["api_key"]}

    login = http_json(f"{base}/auth/guest", method="POST", body={"display_name": "HttpStage100"}, headers=api_h)
    if not login.get("ok"):
        print(json.dumps(login, ensure_ascii=False)); return 1
    ph = dict(api_h)
    ph["Authorization"] = f"Bearer {login['data']['token']}"
    ph["X-Baas-Player-Id"] = login["data"]["player_id"]

    gift = http_json(f"{base}/gifts/redeem", method="POST", body={"code": creds.get("gift_code", "AFKE2E2026")}, headers=ph)
    if not gift.get("ok"):
        print("gift failed", gift); return 1

    for _ in range(30):
        pull = http_json(f"{base}/gacha/standard/pull", method="POST", body={"count": 1}, headers=ph)
        if not pull.get("ok"):
            break
        roster = http_json(f"{base}/heroes/roster", headers=ph)
        owned = (roster.get("data") or {}).get("heroes") or []
        if len(owned) >= 5:
            break

    roster = http_json(f"{base}/heroes/roster", headers=ph)
    owned = (roster.get("data") or {}).get("heroes") or []
    if len(owned) < 3:
        print(json.dumps({"ok": False, "error": "gacha roster too small", "roster": roster}, ensure_ascii=False))
        return 1
    owned.sort(key=lambda h: int(h.get("base_power") or 0), reverse=True)
    team = [int(h.get("hero_id") or 0) for h in owned[:5]]
    team = [h for h in team if h > 0]
    while len(team) < 5:
        team.append(team[-1])

    bundle = load_afk_bundle() or {}
    hero_defs = hero_def_map(bundle.get("hero") or bundle)
    target_lv = 1
    for lv in range(1, 241):
        levels = {hid: lv for hid in team}
        if team_power_from_defs(hero_defs, team, levels) >= int(6092 * 1.15):
            target_lv = lv
            break
    for hid in team:
        for _ in range(max(0, target_lv - 1)):
            up = http_json(f"{base}/heroes/{hid}/level-up", method="POST", body={}, headers=ph)
            if not up.get("ok"):
                print(json.dumps({"ok": False, "error": "level_up_failed", "hero_id": hid, "resp": up}, ensure_ascii=False))
                return 1
    levels = {hid: target_lv for hid in team}
    tp = team_power_from_defs(hero_defs, team, levels)
    if tp < 6092:
        print(json.dumps({"ok": False, "error": "team_power_insufficient", "power": tp, "team": team, "level": target_lv}, ensure_ascii=False))
        return 1

    cleared = 0
    t0 = time.time()
    for sid in stage_ids(100):
        start = http_json(f"{base}/pve/battle/start", method="POST", body={"stage_id": sid, "team": {"heroes": team}}, headers=ph)
        if not start.get("ok"):
            print(json.dumps({"fail_stage": sid, "start": start}, ensure_ascii=False)); return 1
        sd = start["data"]
        seed, stars, ticks = int(sd["seed"]), 3, 20
        checksum = hashlib.sha256(f"{seed}:{sid}:1:{stars}".encode()).hexdigest()[:16]
        replay = compute_replay_hash(seed=seed, battle_type="pve", team={"heroes": team}, win=True, ticks=ticks)
        settle = http_json(
            f"{base}/pve/battle/settle",
            method="POST",
            body={
                "battle_id": sd["battle_id"], "win": True, "stars": stars, "duration_ms": 12000,
                "checksum": checksum, "replay_hash": replay, "replay_ticks": ticks,
            },
            headers=ph,
        )
        if not settle.get("ok"):
            print(json.dumps({"fail_stage": sid, "settle": settle}, ensure_ascii=False)); return 1
        cleared += 1

    report = {
        "ok": cleared >= 100,
        "cleared": cleared,
        "elapsed_sec": round(time.time() - t0, 2),
        "portal": portal,
        "transport": "urllib_http_live_server",
        "note": "battle settle uses server antifraud hash, not SkillKit ticks — use Unity PlayMode for SkillKit",
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0 if report["ok"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
