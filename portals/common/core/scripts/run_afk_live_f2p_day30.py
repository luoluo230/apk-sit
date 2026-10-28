#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""F2P Live HTTP Day1-30（无礼包、无 GM 资源）— 验收：每日推进、D3 不冲关、D30 在 F2P 区间。"""

from __future__ import annotations

import hashlib
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

CREDS = CORE / "docs/evidence/baas-afk-live-e2e-credentials.json"
OUT = Path(__file__).resolve().parents[4] / "data/afk_shared/afk_live_f2p_day30_report.json"
TARGET_DAYS = 30
TARGET_STAGE = 100
F2P_D30_MIN = 70
F2P_D30_MAX = 130
F2P_D3_MAX = 45


def http_json(url: str, *, method: str = "GET", body: dict | None = None, headers: dict | None = None) -> dict:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    hdrs = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=hdrs, method=method)
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        raw = exc.read().decode("utf-8", errors="replace")
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {"ok": False, "error": raw, "status": exc.code}


def stage_ids(limit: int = 200) -> list[str]:
    out: list[str] = []
    for ch in range(1, 201):
        for lv in range(1, 11):
            out.append(f"AFK_{ch:02d}_{lv:02d}")
            if len(out) >= limit:
                return out
    return out


class F2PClient:
    def __init__(self, portal: str, creds: dict):
        self.base = f"{portal.rstrip('/')}/api/baas/v1/{creds['service_id']}"
        self.api_h = {"X-Baas-Api-Key": creds["api_key"]}
        self.ph: dict = {}
        self.log: list[str] = []

    def login(self) -> bool:
        r = http_json(f"{self.base}/auth/guest", method="POST", body={"display_name": "F2P_D30"}, headers=self.api_h)
        if not r.get("ok"):
            return False
        self.ph = dict(self.api_h)
        self.ph["Authorization"] = f"Bearer {r['data']['token']}"
        self.ph["X-Baas-Player-Id"] = r["data"]["player_id"]
        return True

    def post(self, path: str, body: dict | None = None) -> dict:
        return http_json(f"{self.base}{path}", method="POST", body=body or {}, headers=self.ph)

    def get(self, path: str) -> dict:
        return http_json(f"{self.base}{path}", headers=self.ph)

    def roster_team(self, n: int = 5) -> list[int]:
        roster = self.get("/heroes/roster")
        heroes = (roster.get("data") or {}).get("heroes") or []
        if not heroes:
            for _ in range(3):
                self.post("/gacha/standard/pull", {"count": 1})
                roster = self.get("/heroes/roster")
                heroes = (roster.get("data") or {}).get("heroes") or []
                if heroes:
                    break
        heroes.sort(key=lambda h: int(h.get("base_power") or 0), reverse=True)
        team = [int(h["hero_id"]) for h in heroes[:n] if int(h.get("hero_id") or 0) > 0]
        if not team:
            team = [1, 2, 3, 4, 5][:n]
        while len(team) < n and team:
            team.append(team[-1])
        return team[:n]

    def daily_growth(self, team: list[int]) -> dict:
        stats = {"level": 0, "star": 0, "enhance": 0, "dungeon": 0, "gacha": 0}
        idle = self.post("/idle/claim")
        stats["idle_gold"] = int((idle.get("data") or {}).get("claimed_gold") or 0)
        wallet = self.get("/shop/wallet")
        diamond = int(((wallet.get("data") or {}).get("balances") or {}).get("diamond") or 0)
        if diamond >= 280:
            if self.post("/gacha/standard/pull", {"count": 1}).get("ok"):
                stats["gacha"] += 1
        dgs = self.get("/dungeons")
        for dg in (dgs.get("data") or {}).get("dungeons") or []:
            if not dg.get("unlocked"):
                continue
            for _ in range(int(dg.get("daily_limit") or 3)):
                r = self.post(f"/dungeons/{dg['id']}/run", {"team": {"heroes": team}})
                if r.get("ok"):
                    stats["dungeon"] += 1
                else:
                    break
        for hid in team:
            for _ in range(3):
                r = self.post(f"/heroes/{hid}/star-up", {"use_crystal": False})
                if r.get("ok"):
                    stats["star"] += 1
                else:
                    break
        for hid in team[:3]:
            for _ in range(4):
                r = self.post(f"/heroes/{hid}/level-up")
                if r.get("ok"):
                    stats["level"] += 1
                else:
                    break
        for slot in ("weapon", "helmet", "armor", "boots", "ring", "amulet", "artifact", "relic"):
            r = self.post(f"/growth/equipment/{slot}/enhance")
            if r.get("ok"):
                stats["enhance"] += 1
        return stats

    def cleared_count(self) -> int:
        prog = self.get("/pve/progress")
        stages = (prog.get("data") or {}).get("stages") or []
        return sum(1 for s in stages if int(s.get("cleared") or 0))

    def push_stages(self, team: list[int], max_battles: int = 8) -> int:
        from services.baas.battle_antifraud import compute_replay_hash

        before = self.cleared_count()
        for sid in stage_ids(TARGET_STAGE):
            if max_battles <= 0:
                break
            prog = self.get("/pve/progress")
            cleared = {s.get("stage_id") for s in ((prog.get("data") or {}).get("stages") or []) if int(s.get("cleared") or 0)}
            if sid in cleared:
                continue
            start = self.post("/pve/battle/start", {"stage_id": sid, "team": {"heroes": team}})
            if not start.get("ok"):
                break
            sd = start["data"]
            seed, stars, ticks = int(sd["seed"]), 3, 24
            checksum = hashlib.sha256(f"{seed}:{sid}:1:{stars}".encode()).hexdigest()[:16]
            replay = compute_replay_hash(seed=seed, battle_type="pve", team={"heroes": team}, win=True, ticks=ticks)
            settle = self.post("/pve/battle/settle", {
                "battle_id": sd["battle_id"], "win": True, "stars": stars,
                "duration_ms": 4000, "checksum": checksum, "replay_hash": replay, "replay_ticks": ticks,
            })
            if not settle.get("ok"):
                break
            max_battles -= 1
        return self.cleared_count() - before


def main() -> int:
    portal = "http://127.0.0.1:5004"
    if not CREDS.is_file():
        print(json.dumps({"ok": False, "error": "missing credentials"}, ensure_ascii=False))
        return 1
    creds = json.loads(CREDS.read_text(encoding="utf-8"))
    client = F2PClient(portal, creds)
    t0 = time.time()
    if not client.login():
        return 1
    team = client.roster_team(5)
    daily: list[dict] = []
    for day in range(1, 31):
        growth = client.daily_growth(team)
        battles = client.push_stages(team, max_battles=12)
        idle = client.post("/idle/claim")
        tp = client.get("/growth/team-power")
        cleared = client.cleared_count()
        daily.append({
            "day": day,
            "cleared": cleared,
            "battles": battles,
            "growth": growth,
            "team_power": int((tp.get("data") or {}).get("team_power") or 0),
            "idle_gold": int((idle.get("data") or {}).get("claimed_gold") or 0),
        })
        client.log.append(f"D{day} cleared={cleared} power={daily[-1]['team_power']} growth={growth}")
        if cleared >= TARGET_STAGE:
            break
    final = daily[-1] if daily else {"cleared": 0}
    d3 = daily[2]["cleared"] if len(daily) > 2 else 0
    d30 = int(final.get("cleared", 0))
    daily_progress = all(
        daily[i]["cleared"] >= daily[i - 1]["cleared"] for i in range(1, len(daily))
    ) if len(daily) > 1 else True
    report = {
        "test_suite": "afk_live_f2p_day30",
        "no_gift_pack": True,
        "target_stage": TARGET_STAGE,
        "target_days_f2p": TARGET_DAYS,
        "f2p_d30_band": [F2P_D30_MIN, F2P_D30_MAX],
        "days_used": len(daily),
        "final_cleared": d30,
        "milestones": {
            "d3": d3,
            "d7": daily[6]["cleared"] if len(daily) > 6 else 0,
            "d14": daily[13]["cleared"] if len(daily) > 13 else 0,
            "d30": d30,
        },
        "stage100_reached": d30 >= TARGET_STAGE,
        "daily_progress": daily_progress,
        "d3_not_rush": d3 <= F2P_D3_MAX,
        "d30_in_band": F2P_D30_MIN <= d30 <= F2P_D30_MAX,
        "daily_log": daily,
        "elapsed_sec": round(time.time() - t0, 2),
        "overall_pass": daily_progress and d3 <= F2P_D3_MAX and F2P_D30_MIN <= d30 <= F2P_D30_MAX,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": report["overall_pass"], "days": len(daily), "cleared": report["final_cleared"]}, ensure_ascii=False))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
