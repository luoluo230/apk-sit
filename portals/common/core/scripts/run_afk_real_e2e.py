#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AFK 真实 BaaS 联调：Flask test_client 走完整 HTTP 链路
(auth → gacha → hero level-up → pve start/settle → tower → idle)
目标：三档品质阵容各推至第 100 关，输出 JSON 报告。
"""

from __future__ import annotations

import hashlib
import json
import os
import sys
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional, Tuple

_CORE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_REPO = os.path.dirname(os.path.dirname(os.path.dirname(_CORE)))
if _CORE not in sys.path:
    sys.path.insert(0, _CORE)

os.environ.setdefault("APK_DEBUG", "false")
os.environ.setdefault("FORCE_LOGIN", "false")

from config import load_dotenv

load_dotenv()

from app_new import app  # noqa: E402
from models.db import get_cursor, init_db  # noqa: E402
from services.baas.afk_config_loader import load_afk_bundle, afk_formulas  # noqa: E402
from services.baas.afk_formula_engine import team_power_from_defs  # noqa: E402
from services.baas.battle_antifraud import compute_replay_hash, team_power  # noqa: E402
from services.baas.registry import default_feature_configs  # noqa: E402
from services.baas.service_crud import ensure_service, update_service  # noqa: E402
from services.baas.wallet_helpers import credit_wallet  # noqa: E402

_TEST_PROJECT = "test_baas_afk_real_e2e"
_GAME_ID = "baas-afk-real-e2e-game"
_GAME_KEY = "baas-afk-real-e2e-key"
TARGET_STAGE = 100
OUT_JSON = os.path.join(_REPO, "data", "afk_shared", "real_e2e_report.json")


@dataclass
class ProfileResult:
    name: str
    target_quality: int
    player_id: str
    max_cleared: int = 0
    gacha_pulls: int = 0
    level_ups: int = 0
    pve_battles: int = 0
    tower_floor: int = 0
    errors: List[str] = field(default_factory=list)
    milestones: List[Dict[str, Any]] = field(default_factory=list)
    final_team_power: int = 0
    final_gold: int = 0

    @property
    def stage100_reached(self) -> bool:
        return self.max_cleared >= TARGET_STAGE


def _ordered_stages(bundle: Dict[str, Any], limit: int = TARGET_STAGE) -> List[Dict[str, Any]]:
    stages = list((bundle.get("pve") or {}).get("stages") or [])
    ordered = sorted(stages, key=lambda s: (int(s.get("chapter") or 0), int(s.get("stage") or 0)))
    return ordered[:limit]


def _hero_defs(bundle: Dict[str, Any]) -> Dict[int, Dict[str, Any]]:
    rows = (bundle.get("hero") or {}).get("hero_defs") or []
    return {int(r["id"]): r for r in rows if int(r.get("id") or 0) > 0}


def _setup_service() -> Tuple[str, str]:
    from models.data import projects_db
    from repositories.admin import projects_repo

    projects_db[_TEST_PROJECT] = {
        "name": "AFK Real E2E",
        "game_id": _GAME_ID,
        "game_key": _GAME_KEY,
        "server_mode": "casual_baas",
        "status": "active",
        "created_by": "admin",
    }
    projects_repo.upsert_project(_TEST_PROJECT, projects_db[_TEST_PROJECT])
    svc, api_secret = ensure_service(_TEST_PROJECT, "development", actor="admin")
    service_id = svc["service_id"]
    flags = {k: True for k in (
        "login", "hero", "gacha", "idle", "tower", "iap", "pve", "economy", "inventory",
    )}
    update_service(
        _TEST_PROJECT,
        service_id,
        {"feature_flags": flags, "feature_configs": default_feature_configs()},
        actor="admin",
    )
    if not api_secret:
        from services.baas.service_crud import rotate_api_secret
        api_secret, _ = rotate_api_secret(_TEST_PROJECT, service_id)
    return service_id, api_secret


def _login(client, service_id: str, api_secret: str, name: str) -> Tuple[str, Dict[str, str], str]:
    base = f"/api/baas/v1/{service_id}"
    headers = {"X-Baas-Api-Key": api_secret, "Content-Type": "application/json"}
    resp = client.post(f"{base}/auth/guest", headers=headers, data=json.dumps({"display_name": name}))
    if resp.status_code != 200 or not resp.get_json().get("ok"):
        raise RuntimeError(f"guest login failed: {resp.get_json()}")
    data = resp.get_json()["data"]
    player_headers = dict(headers)
    player_headers["Authorization"] = f"Bearer {data['token']}"
    player_headers["X-Baas-Player-Id"] = data["player_id"]
    return base, player_headers, data["player_id"]


def _gm_credit(service_id: str, player_id: str, gold: int, diamond: int) -> None:
    init_db()
    with get_cursor() as cur:
        credit_wallet(cur, service_id, player_id, "gold", gold)
        credit_wallet(cur, service_id, player_id, "diamond", diamond)


def _refill_stamina_http(client, base: str, headers: Dict[str, str], service_id: str, player_id: str) -> None:
    """通过服务端体力恢复逻辑补满：写入过期 updated_at 后 GET /pve/stamina。"""
    from services.baas.helpers import _json_dump
    from services.baas.pve_service import _save_stamina
    from services.baas.service_crud import get_feature_config

    cfg = get_feature_config(service_id, "pve")
    max_stamina = int(cfg.get("stamina_max") or 120)
    past = (datetime.now(timezone.utc) - timedelta(hours=48)).strftime("%Y-%m-%dT%H:%M:%SZ")
    init_db()
    with get_cursor() as cur:
        _save_stamina(cur, service_id, player_id, {"current": 0, "updated_at": past, "max": max_stamina})
    resp = client.get(f"{base}/pve/stamina", headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"stamina refresh failed: {resp.get_json()}")


def _api_json(resp) -> Dict[str, Any]:
    return resp.get_json() or {}


def _gacha_pulls(client, base: str, headers: Dict[str, str], count: int) -> int:
    done = 0
    for _ in range(count):
        resp = client.post(
            f"{base}/gacha/standard/pull",
            headers=headers,
            data=json.dumps({"count": 1}),
        )
        body = _api_json(resp)
        if resp.status_code == 200 and body.get("ok"):
            done += 1
        elif "钻石" in str(body.get("error") or ""):
            break
        else:
            break
    return done


def _get_roster(client, base: str, headers: Dict[str, str]) -> List[Dict[str, Any]]:
    resp = client.get(f"{base}/heroes/roster", headers=headers)
    if resp.status_code != 200 or not _api_json(resp).get("ok"):
        raise RuntimeError(f"roster failed: {_api_json(resp)}")
    return list(_api_json(resp)["data"].get("heroes") or [])


def _pick_team(heroes: List[Dict[str, Any]], defs: Dict[int, Dict[str, Any]], target_q: int) -> List[int]:
    ranked = []
    for h in heroes:
        hid = int(h["hero_id"])
        meta = defs.get(hid, {})
        q = int(meta.get("quality") or 3)
        score = h.get("base_power") or 0
        if q == target_q:
            score += 500
        elif abs(q - target_q) == 1:
            score += 200
        ranked.append((score, hid))
    ranked.sort(reverse=True)
    ids = [hid for _, hid in ranked[:5]]
    return ids if ids else [int(h["hero_id"]) for h in heroes[:5]]


def _target_level_for_power(
    defs: Dict[int, Dict[str, Any]],
    team_ids: List[int],
    target_power: int,
    formulas: Dict[str, str],
) -> int:
    lo, hi = 1, 240
    while lo < hi:
        mid = (lo + hi) // 2
        levels = {hid: mid for hid in team_ids}
        tp = team_power_from_defs(defs, team_ids, levels, formulas=formulas)
        if tp >= target_power:
            hi = mid
        else:
            lo = mid + 1
    return lo


def _boost_team_http(
    client,
    base: str,
    headers: Dict[str, str],
    team_ids: List[int],
    target_level: int,
) -> int:
    roster = {int(h["hero_id"]): int(h["level"]) for h in _get_roster(client, base, headers)}
    ups = 0
    for hid in team_ids:
        cur = roster.get(hid, 1)
        while cur < target_level:
            if not _level_up_once(client, base, headers, hid):
                break
            cur += 1
            ups += 1
    return ups


def _level_up_once(client, base: str, headers: Dict[str, str], hero_id: int) -> bool:
    resp = client.post(f"{base}/heroes/{hero_id}/level-up", headers=headers, data="{}")
    body = _api_json(resp)
    return resp.status_code == 200 and body.get("ok")


def _wallet_gold(client, base: str, headers: Dict[str, str]) -> int:
    resp = client.get(f"{base}/shop/wallet", headers=headers)
    if resp.status_code != 200:
        return 0
    data = _api_json(resp).get("data") or {}
    balances = data.get("balances") or data.get("currencies") or data
    if isinstance(balances, dict):
        for k, v in balances.items():
            if str(k) == "gold":
                return int(v if isinstance(v, (int, float)) else (v.get("balance") if isinstance(v, dict) else 0))
    if isinstance(balances, list):
        for row in balances:
            if isinstance(row, dict) and str(row.get("currency_id")) == "gold":
                return int(row.get("balance") or 0)
    return 0


def _pve_settle(
    client,
    base: str,
    headers: Dict[str, str],
    battle_id: str,
    seed: int,
    stage_id: str,
    team: Dict[str, Any],
) -> Dict[str, Any]:
    win, stars, ticks = True, 3, 24
    checksum = hashlib.sha256(f"{seed}:{stage_id}:{int(win)}:{stars}".encode()).hexdigest()[:16]
    replay_hash = compute_replay_hash(seed=seed, battle_type="pve", team=team, win=win, ticks=ticks)
    resp = client.post(
        f"{base}/pve/battle/settle",
        headers=headers,
        data=json.dumps({
            "battle_id": battle_id,
            "win": win,
            "stars": stars,
            "duration_ms": 12000,
            "checksum": checksum,
            "replay_hash": replay_hash,
            "replay_ticks": ticks,
        }),
    )
    body = _api_json(resp)
    if resp.status_code != 200 or not body.get("ok"):
        raise RuntimeError(f"settle failed stage={stage_id}: {body}")
    return body["data"]


def _run_profile(
    client,
    service_id: str,
    api_secret: str,
    bundle: Dict[str, Any],
    name: str,
    target_quality: int,
) -> ProfileResult:
    result = ProfileResult(name=name, target_quality=target_quality, player_id="")
    defs = _hero_defs(bundle)
    stages = _ordered_stages(bundle, TARGET_STAGE)

    base, headers, player_id = _login(client, service_id, api_secret, name)
    result.player_id = player_id
    _gm_credit(service_id, player_id, gold=5_000_000, diamond=50_000)

    result.gacha_pulls = _gacha_pulls(client, base, headers, 15)
    roster = _get_roster(client, base, headers)
    if not roster:
        result.errors.append("gacha 未获得任何英雄")
        return result

    team_ids = _pick_team(roster, defs, target_quality)
    team = {"heroes": team_ids}
    formulas = dict(afk_formulas() or {})

    max_required = int(stages[-1].get("power_required") or 6092)
    target_lv = _target_level_for_power(defs, team_ids, int(max_required * 1.05), formulas)
    print(f"[{name}] gacha={result.gacha_pulls} team={team_ids} target_level={target_lv}", flush=True)
    result.level_ups = _boost_team_http(client, base, headers, team_ids, target_lv)

    cleared_ids: set = set()
    stage_index = 0

    while stage_index < len(stages) and len(cleared_ids) < TARGET_STAGE:
        stage = stages[stage_index]
        stage_id = str(stage["id"])
        required = int(stage.get("power_required") or 0)

        if stage_index % 12 == 0:
            _refill_stamina_http(client, base, headers, service_id, player_id)

        start_resp = client.post(
            f"{base}/pve/battle/start",
            headers=headers,
            data=json.dumps({"stage_id": stage_id, "team": team}),
        )
        start_body = _api_json(start_resp)
        if start_resp.status_code != 200 or not start_body.get("ok"):
            err = str(start_body.get("error") or start_body)
            if "体力" in err:
                _refill_stamina_http(client, base, headers, service_id, player_id)
                continue
            if "战力" in err:
                result.level_ups += _boost_team_http(client, base, headers, team_ids, min(240, target_lv + 5))
                target_lv += 5
                continue
            result.errors.append(f"start 失败 {stage_id}: {err}")
            return result

        start_data = start_body["data"]
        battle_id = start_data["battle_id"]
        seed = int(start_data["seed"])
        result.final_team_power = int(start_data.get("team_power") or 0)

        try:
            settle_data = _pve_settle(client, base, headers, battle_id, seed, stage_id, team)
        except RuntimeError as exc:
            result.errors.append(str(exc))
            return result

        result.pve_battles += 1
        if settle_data.get("win"):
            cleared_ids.add(stage_id)
            result.max_cleared = len(cleared_ids)
            if result.max_cleared in (10, 25, 50, 75, 100):
                result.milestones.append({
                    "stage": result.max_cleared,
                    "stage_id": stage_id,
                    "team_power": result.final_team_power,
                    "required": required,
                })
            stage_index += 1
            if result.max_cleared % 25 == 0:
                print(f"[{name}] cleared={result.max_cleared} power={result.final_team_power}", flush=True)
        else:
            result.errors.append(f"settle 失败 {stage_id}: win=false")
            return result

    result.final_gold = _wallet_gold(client, base, headers)

    # 爬塔 1 层（真实 tower API）
    try:
        t_start = client.post(
            f"{base}/tower/main/battle/start",
            headers=headers,
            data=json.dumps({"floor": 1, "team": team}),
        )
        if t_start.status_code == 200 and _api_json(t_start).get("ok"):
            td = _api_json(t_start)["data"]
            seed = int(td["seed"])
            checksum = hashlib.sha256(f"{seed}:main:1:{1}".encode()).hexdigest()[:16]
            replay = compute_replay_hash(seed=seed, battle_type="tower", team=team, win=True, ticks=20)
            t_settle = client.post(
                f"{base}/tower/battle/settle",
                headers=headers,
                data=json.dumps({
                    "battle_id": td["battle_id"],
                    "win": True,
                    "stars": 1,
                    "duration_ms": 8000,
                    "checksum": checksum,
                    "replay_hash": replay,
                    "replay_ticks": 20,
                }),
            )
            if t_settle.status_code == 200 and _api_json(t_settle).get("ok"):
                result.tower_floor = 1
    except Exception as exc:
        result.errors.append(f"tower: {exc}")

    return result


def run_real_e2e() -> Dict[str, Any]:
    t0 = time.time()
    init_db()
    bundle = load_afk_bundle() or {}
    service_id, api_secret = _setup_service()

    app.config["WTF_CSRF_ENABLED"] = False
    client = app.test_client()

    profiles = [
        _run_profile(client, service_id, api_secret, bundle, "blue_http", 3),
        _run_profile(client, service_id, api_secret, bundle, "purple_http", 4),
        _run_profile(client, service_id, api_secret, bundle, "orange_http", 5),
    ]

    report = {
        "test_type": "real_baas_http_e2e",
        "server": "Flask app.test_client (app_new + baas_public_bp)",
        "bundle_version": bundle.get("version"),
        "target_stage": TARGET_STAGE,
        "elapsed_sec": round(time.time() - t0, 2),
        "profiles": [
            {
                "name": p.name,
                "target_quality": p.target_quality,
                "player_id": p.player_id,
                "max_cleared": p.max_cleared,
                "stage100_reached": p.stage100_reached,
                "gacha_pulls": p.gacha_pulls,
                "level_ups": p.level_ups,
                "pve_battles": p.pve_battles,
                "tower_floor": p.tower_floor,
                "final_team_power": p.final_team_power,
                "final_gold": p.final_gold,
                "milestones": p.milestones,
                "errors": p.errors,
            }
            for p in profiles
        ],
        "overall_pass": all(p.stage100_reached and not p.errors for p in profiles),
    }
    os.makedirs(os.path.dirname(OUT_JSON), exist_ok=True)
    with open(OUT_JSON, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    return report


if __name__ == "__main__":
    rep = run_real_e2e()
    print(json.dumps(rep, ensure_ascii=False, indent=2))
    print("PASS" if rep["overall_pass"] else "FAIL")
    print("report:", OUT_JSON)
    sys.exit(0 if rep["overall_pass"] else 1)
