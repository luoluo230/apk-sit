"""Authoritative account progress and the AFK home presentation contract."""
from __future__ import annotations
import json
from datetime import datetime, timezone
from pathlib import Path
from models.db import get_cursor, init_db
from services.baas.helpers import _json_dump, _json_load, _now_iso
from services.baas.afk.afk_config_loader import _REPO_ROOT


def rules():
    path = _REPO_ROOT / "data" / "afk_shared" / "afk_home_economy.json"
    return json.loads(path.read_text(encoding="utf-8-sig"))


def account_progress(total, cfg=None):
    cfg = cfg or rules()
    remaining = max(0, int(total))
    level = 1
    cap = max(1, int(cfg["account_level_cap"]))
    step = max(1, int(cfg["account_exp_per_level"]))
    while level < cap and remaining >= level * step:
        remaining -= level * step
        level += 1
    required = level * step if level < cap else 0
    return {"account_exp_total": max(0, int(total)), "account_level": level,
            "account_exp": min(remaining, required - 1) if required else 0,
            "account_exp_required": required}


def _account(cur, service_id, player_id):
    row = cur.execute("SELECT value_json FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
                      (service_id, player_id, "_afk_account_progress")).fetchone()
    return _json_load(row["value_json"] if row else "{}", {})


def grant_account_exp(cur, service_id, player_id, amount):
    key = "_afk_account_progress"
    cur.execute("""INSERT INTO baas_player_data (service_id,player_id,data_key,value_json,version,updated_at)
        VALUES (?,?,?,?,?,?) ON CONFLICT(service_id,player_id,data_key) DO NOTHING""",
        (service_id,player_id,key,'{"total_exp":0}',1,_now_iso()))
    for _ in range(4):
        row = cur.execute("SELECT value_json,version FROM baas_player_data WHERE service_id=? AND player_id=? AND data_key=?",
                          (service_id,player_id,key)).fetchone()
        state = _json_load(row["value_json"], {})
        state["total_exp"] = max(0,int(state.get("total_exp",0))) + max(0,int(amount))
        applied = cur.execute("""UPDATE baas_player_data SET value_json=?,version=version+1,updated_at=?
            WHERE service_id=? AND player_id=? AND data_key=? AND version=? RETURNING version""",
            (_json_dump(state),_now_iso(),service_id,player_id,key,row["version"])).fetchone()
        if applied is not None: return account_progress(state["total_exp"])
    raise ValueError("账号经验同步繁忙，请重试结算")


def ensure_idle_started(cur, service_id, player_id):
    now = _now_iso()
    cur.execute("""INSERT INTO baas_idle_state (service_id,player_id,last_claim_at,updated_at)
        VALUES (?,?,?,?) ON CONFLICT(service_id,player_id) DO NOTHING""", (service_id,player_id,now,now))


def utc_ticks(iso=None):
    now = datetime.fromisoformat(str(iso).replace("Z", "+00:00")) if iso else datetime.now(timezone.utc)
    if now.tzinfo is None: now = now.replace(tzinfo=timezone.utc)
    delta = now - datetime(1, 1, 1, tzinfo=timezone.utc)
    return (delta.days * 86400 + delta.seconds) * 10000000 + delta.microseconds * 10


def get_home(service_id, player_id):
    from services.baas import idle_service, pve_service
    idle = idle_service.get_status(service_id, player_id)
    stamina = pve_service.get_stamina(service_id, player_id)["stamina"]
    init_db()
    with get_cursor() as cur:
        account = account_progress(_account(cur, service_id, player_id).get("total_exp", 0))
        rows = cur.execute("SELECT currency_id,balance FROM baas_wallets WHERE service_id=? AND player_id=?",
                           (service_id,player_id)).fetchall()
    wallet = {str(row["currency_id"]): int(row["balance"] or 0) for row in rows}
    return dict(account, schema_version=1, server_utc_ticks=utc_ticks(),
        gold=wallet.get("gold",0), diamond=wallet.get("diamond",0),
        stamina_current=int(stamina["current"]), stamina_max=int(stamina["max"]),
        stamina_recover_seconds=int(stamina["recover_seconds"]),
        max_cleared_stage=int(idle.get("max_cleared_stage",0)),
        idle_eligible=bool(idle.get("eligible")), idle_minutes=int(idle.get("accumulated_minutes",0)),
        idle_max_minutes=int(idle.get("max_minutes",rules()["idle_max_minutes"])),
        idle_gold_per_hour=int(idle.get("gold_per_hour",0)),
        idle_exp_per_hour=int(idle.get("account_exp_per_hour",0)),
        idle_diamond_per_hour=int(idle.get("diamond_per_hour",0)),
        idle_gold=int(idle.get("estimated_gold",0)), idle_exp=int(idle.get("estimated_account_exp",0)),
        idle_diamond=int(idle.get("estimated_diamond",0)),
        last_claim_utc_ticks=utc_ticks(idle["last_claim_at"]) if idle.get("last_claim_at") else 0)
