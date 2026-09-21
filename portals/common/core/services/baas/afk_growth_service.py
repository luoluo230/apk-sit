# -*- coding: utf-8 -*-
"""AFK 装备成长 / 升星 / 天赋 / 副本 — BaaS 服务端实现。"""

from __future__ import annotations

import random
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

from models.db import get_cursor, init_db
from services.baas.afk_config_loader import afk_formulas, hero_def_map, load_afk_bundle
from services.baas.afk_economy_service import _economy_cfg, equip_growth_config
from services.baas.afk_formula_engine import eval_formula, hero_stats, team_power_from_defs
from services.baas.helpers import _json_dump, _json_load, _now_iso
from services.baas.pve_service import get_progress, get_stamina
from services.baas.service_crud import feature_enabled, get_feature_config
from services.baas.wallet_helpers import credit_wallet, debit_wallet
from services.baas import inventory_service

EQUIP_SLOTS = ("helmet", "chest", "legs", "bracers", "greaves", "jewelry", "weapon", "offhand")


def _utc_today() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def _formulas() -> Dict[str, str]:
    bundle = load_afk_bundle() or {}
    eco = bundle.get("economy_system") or {}
    merged = dict(afk_formulas())
    for k, v in (eco.get("formulas") or {}).items():
        merged[str(k)] = str(v)
    return merged


def _max_cleared_stage(progress: Dict[str, Any]) -> int:
    best = 0
    for row in progress.get("stages") or []:
        if int(row.get("cleared") or 0) <= 0:
            continue
        sid = str(row.get("stage_id") or "")
        if sid.startswith("AFK_"):
            try:
                parts = sid.split("_")
                num = (int(parts[1]) - 1) * 10 + int(parts[2])
                best = max(best, num)
            except (IndexError, ValueError):
                pass
        elif sid and sid[0].isdigit():
            try:
                ch, st = sid.split("-", 1)
                best = max(best, (int(ch) - 1) * 10 + int(st))
            except (ValueError, IndexError):
                pass
    return best


def _dungeon_def(service_id: str, dungeon_id: str) -> Dict[str, Any]:
    for dg in _economy_cfg(service_id).get("dungeons") or []:
        if str(dg.get("id") or "") == str(dungeon_id):
            return dict(dg)
    raise ValueError("副本不存在")


def _ensure_equipment(cur, service_id: str, player_id: str, *, quality: int = 3) -> None:
    now = _now_iso()
    for slot in EQUIP_SLOTS:
        row = cur.execute(
            "SELECT slot FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot),
        ).fetchone()
        if not row:
            cur.execute(
                """
                INSERT INTO baas_player_equipment
                (service_id, player_id, slot, quality, enhance_level, refine_level, awaken, gem_count, affix_seed, updated_at)
                VALUES (?,?,?,?,0,0,0,0,0,?)
                """,
                (service_id, player_id, slot, int(quality), now),
            )


def _load_equipment(cur, service_id: str, player_id: str) -> List[Dict[str, Any]]:
    _ensure_equipment(cur, service_id, player_id)
    rows = cur.execute(
        """
        SELECT slot, quality, enhance_level, refine_level, awaken, gem_count, affix_seed, updated_at
        FROM baas_player_equipment WHERE service_id=? AND player_id=?
        ORDER BY slot
        """,
        (service_id, player_id),
    ).fetchall()
    return [dict(r) for r in rows]


def _equip_power_bonus(equipment: List[Dict[str, Any]]) -> int:
    bonus = 0
    for eq in equipment:
        bonus += int(eq.get("enhance_level") or 0) * 8
        bonus += int(eq.get("refine_level") or 0) * 15
        bonus += 40 if int(eq.get("awaken") or 0) else 0
        bonus += int(eq.get("gem_count") or 0) * 5
    return bonus


def _hero_rows(cur, service_id: str, player_id: str) -> List[Any]:
    return cur.execute(
        """
        SELECT hero_id, level, star, shards, talent_points
        FROM baas_player_heroes WHERE service_id=? AND player_id=?
        ORDER BY hero_id
        """,
        (service_id, player_id),
    ).fetchall()


def estimate_team_power(
    service_id: str,
    player_id: str,
    *,
    team_ids: Optional[List[int]] = None,
) -> Dict[str, Any]:
    from services.baas.afk_power_service import team_power_unified
    return team_power_unified(service_id, player_id, team_ids=team_ids)


def get_equipment_state(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    init_db()
    with get_cursor() as cur:
        items = _load_equipment(cur, service_id, player_id)
    return {"equipment": items, "slots": list(EQUIP_SLOTS), "growth": equip_growth_config(service_id)}


def _consume_item_key(cur, service_id: str, player_id: str, item_key: str, qty: int = 1) -> None:
    if not feature_enabled(service_id, "inventory"):
        raise ValueError("背包功能未启用")
    key = str(item_key or "").strip()
    cost = max(1, int(qty or 1))
    row = cur.execute(
        """
        SELECT item_uid, quantity FROM baas_player_inventory
        WHERE service_id=? AND player_id=? AND item_def_id=? AND quantity > 0
        ORDER BY updated_at LIMIT 1
        """,
        (service_id, player_id, key),
    ).fetchone()
    if not row or int(row["quantity"] or 0) < cost:
        raise ValueError(f"道具不足: {key}")
    remain = int(row["quantity"]) - cost
    now = _now_iso()
    if remain <= 0:
        cur.execute("DELETE FROM baas_player_inventory WHERE item_uid=?", (row["item_uid"],))
    else:
        cur.execute(
            "UPDATE baas_player_inventory SET quantity=?, updated_at=? WHERE item_uid=?",
            (remain, now, row["item_uid"]),
        )


def _grant_rewards(cur, service_id: str, player_id: str, rewards: Dict[str, Any]) -> Dict[str, Any]:
    out: Dict[str, Any] = {}
    for k, v in (rewards or {}).items():
        if k in ("gold", "diamond"):
            credit_wallet(cur, service_id, player_id, k, int(v))
            out[k] = int(v)
        elif feature_enabled(service_id, "inventory"):
            inventory_service.grant_item(cur, service_id, player_id, str(k), quantity=int(v))
            out[k] = int(v)
    return out


def enhance_equipment(service_id: str, player_id: str, slot: str, *, use_luck: bool = False) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    slot_name = str(slot or "").strip()
    if slot_name not in EQUIP_SLOTS:
        raise ValueError("装备槽位无效")
    cfg = equip_growth_config(service_id).get("enhance") or {}
    formulas = _formulas()
    init_db()
    with get_cursor() as cur:
        _ensure_equipment(cur, service_id, player_id)
        row = cur.execute(
            "SELECT * FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot_name),
        ).fetchone()
        if not row:
            raise ValueError("装备不存在")
        quality = int(row["quality"] or 3)
        enhance = int(row["enhance_level"] or 0)
        max_enh = 20
        for q in (_economy_cfg(service_id).get("equip_qualities") or []):
            if int(q.get("id") or 0) == quality:
                max_enh = int(q.get("enhance_max") or max_enh)
                break
        if enhance >= max_enh:
            raise ValueError("已达强化上限")
        cost_g = eval_formula(str(cfg.get("cost_gold_formula") or "equip_enhance_gold"), {"enhance_level": enhance, "quality": quality}, formulas=formulas)
        debit_wallet(cur, service_id, player_id, "gold", cost_g)
        _consume_item_key(cur, service_id, player_id, str(cfg.get("cost_item") or "enhance_stone"), 1)
        fail_from = int(cfg.get("fail_from_level") or 12)
        failed = False
        if enhance >= fail_from - 1:
            fail_rate = eval_formula(
                "fail_rate",
                {"enhance_level": enhance},
                formulas=formulas,
                expr=str(cfg.get("fail_rate_formula") or "max(0, (enhance_level - 11) * 0.025)"),
            )
            rate = fail_rate / 100.0 if fail_rate > 1 else float(fail_rate)
            if random.random() < rate:
                if use_luck:
                    _consume_item_key(cur, service_id, player_id, str(cfg.get("luck_item") or "luck_potion"), 1)
                else:
                    failed = True
        now = _now_iso()
        new_level = enhance if failed else enhance + 1
        cur.execute(
            "UPDATE baas_player_equipment SET enhance_level=?, updated_at=? WHERE service_id=? AND player_id=? AND slot=?",
            (new_level, now, service_id, player_id, slot_name),
        )
    if not failed:
        try:
            from services.baas.afk_retention_hooks import on_enhance
            on_enhance(service_id, player_id, count=1)
        except Exception:
            pass
    return {"slot": slot_name, "enhance_level": new_level, "failed": failed, "spent_gold": cost_g}


def refine_equipment(service_id: str, player_id: str, slot: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    slot_name = str(slot or "").strip()
    if slot_name not in EQUIP_SLOTS:
        raise ValueError("装备槽位无效")
    cfg = equip_growth_config(service_id).get("refine") or {}
    max_lv = int(cfg.get("max_level") or 10)
    formulas = _formulas()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot_name),
        ).fetchone()
        if not row:
            raise ValueError("装备不存在")
        refine = int(row["refine_level"] or 0)
        quality = int(row["quality"] or 3)
        if refine >= max_lv:
            raise ValueError("已达精炼上限")
        cost_g = eval_formula(str(cfg.get("cost_gold_formula") or "equip_refine_gold"), {"refine_level": refine, "quality": quality}, formulas=formulas)
        debit_wallet(cur, service_id, player_id, "gold", cost_g)
        _consume_item_key(cur, service_id, player_id, str(cfg.get("cost_item") or "refine_core"), 1)
        refine += 1
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_equipment SET refine_level=?, updated_at=? WHERE service_id=? AND player_id=? AND slot=?",
            (refine, now, service_id, player_id, slot_name),
        )
    return {"slot": slot_name, "refine_level": refine, "spent_gold": cost_g}


def awaken_equipment(service_id: str, player_id: str, slot: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    slot_name = str(slot or "").strip()
    cfg = equip_growth_config(service_id).get("awaken") or {}
    min_enh = int(cfg.get("require_enhance_min") or 15)
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot_name),
        ).fetchone()
        if not row:
            raise ValueError("装备不存在")
        if int(row["awaken"] or 0):
            raise ValueError("已觉醒")
        if int(row["enhance_level"] or 0) < min_enh:
            raise ValueError(f"需强化至 {min_enh} 级")
        _consume_item_key(cur, service_id, player_id, str(cfg.get("cost_item") or "awaken_stone"), 1)
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_equipment SET awaken=1, updated_at=? WHERE service_id=? AND player_id=? AND slot=?",
            (now, service_id, player_id, slot_name),
        )
    return {"slot": slot_name, "awaken": True}


def reforge_equipment(service_id: str, player_id: str, slot: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    slot_name = str(slot or "").strip()
    cfg = equip_growth_config(service_id).get("reforge") or {}
    formulas = _formulas()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot_name),
        ).fetchone()
        if not row:
            raise ValueError("装备不存在")
        quality = int(row["quality"] or 3)
        cost_g = eval_formula(str(cfg.get("cost_gold_formula") or "equip_reforge_gold"), {"quality": quality}, formulas=formulas)
        debit_wallet(cur, service_id, player_id, "gold", cost_g)
        _consume_item_key(cur, service_id, player_id, str(cfg.get("cost_item") or "weapon_reforge"), 1)
        seed = random.randint(1, 999999)
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_equipment SET affix_seed=?, updated_at=? WHERE service_id=? AND player_id=? AND slot=?",
            (seed, now, service_id, player_id, slot_name),
        )
    return {"slot": slot_name, "affix_seed": seed, "spent_gold": cost_g}


def socket_gem(service_id: str, player_id: str, slot: str, gem_item_id: str = "gem_ruby") -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    slot_name = str(slot or "").strip()
    cfg = equip_growth_config(service_id).get("socket") or {}
    gem = str(gem_item_id or "gem_ruby").strip()
    allowed = {str(x) for x in (cfg.get("gem_items") or ["gem_ruby"])}
    if gem not in allowed:
        raise ValueError("宝石类型无效")
    init_db()
    with get_cursor() as cur:
        # Socketing may be the first equipment-growth action for a player.
        # Keep its initialization contract identical to enhancement instead of
        # requiring an unrelated action to create the equipment rows first.
        _ensure_equipment(cur, service_id, player_id)
        row = cur.execute(
            "SELECT * FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot_name),
        ).fetchone()
        if not row:
            raise ValueError("装备不存在")
        quality = int(row["quality"] or 3)
        max_gems = max(0, quality - 2)
        gems = int(row["gem_count"] or 0)
        if gems >= max_gems:
            raise ValueError("镶嵌槽已满")
        _consume_item_key(cur, service_id, player_id, gem, 1)
        gems += 1
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_equipment SET gem_count=?, updated_at=? WHERE service_id=? AND player_id=? AND slot=?",
            (gems, now, service_id, player_id, slot_name),
        )
    return {"slot": slot_name, "gem_count": gems, "gem_item_id": gem}


def star_up_hero(service_id: str, player_id: str, hero_id: int, *, use_crystal: bool = False) -> Dict[str, Any]:
    if not feature_enabled(service_id, "hero"):
        raise ValueError("英雄系统未启用")
    hero_cfg = get_feature_config(service_id, "hero")
    defs = hero_def_map(hero_cfg)
    hid = int(hero_id or 0)
    meta = defs.get(hid) or {}
    quality = int(meta.get("quality") or 3)
    formulas = _formulas()
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT * FROM baas_player_heroes WHERE service_id=? AND player_id=? AND hero_id=?",
            (service_id, player_id, hid),
        ).fetchone()
        if not row:
            raise ValueError("未拥有该英雄")
        star = int(row["star"] or 1)
        shards = int(row["shards"] or 0)
        if star >= 5:
            raise ValueError("已达星级上限")
        need = eval_formula("star_up_shard_cost", {"star": star, "quality_shard_mul": quality - 2}, formulas=formulas)
        if shards >= need:
            shards -= need
        elif use_crystal:
            crystal_cost = max(1, need // 10)
            _consume_item_key(cur, service_id, player_id, "star_up_crystal", crystal_cost)
        else:
            raise ValueError(f"碎片不足（需要 {need}）")
        star += 1
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_heroes SET star=?, shards=?, updated_at=? WHERE service_id=? AND player_id=? AND hero_id=?",
            (star, shards, now, service_id, player_id, hid),
        )
    return {"hero_id": hid, "star": star, "shards": shards, "spent_shards": need}


def add_talent_point(service_id: str, player_id: str, hero_id: int) -> Dict[str, Any]:
    if not feature_enabled(service_id, "hero"):
        raise ValueError("英雄系统未启用")
    hid = int(hero_id or 0)
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT talent_points FROM baas_player_heroes WHERE service_id=? AND player_id=? AND hero_id=?",
            (service_id, player_id, hid),
        ).fetchone()
        if not row:
            raise ValueError("未拥有该英雄")
        tp = int(row["talent_points"] or 0)
        if tp >= 20:
            raise ValueError("天赋点已达上限")
        _consume_item_key(cur, service_id, player_id, "talent_book", 1)
        tp += 1
        now = _now_iso()
        cur.execute(
            "UPDATE baas_player_heroes SET talent_points=?, updated_at=? WHERE service_id=? AND player_id=? AND hero_id=?",
            (tp, now, service_id, player_id, hid),
        )
    return {"hero_id": hid, "talent_points": tp}


def _dungeon_daily_limit(service_id: str, player_id: str, dg: Dict[str, Any]) -> int:
    limit = int(dg.get("daily_limit") or dg.get("weekly_limit") or 1)
    try:
        from services.baas.afk_vip_service import extra_dungeon_attempts

        limit += extra_dungeon_attempts(service_id, player_id)
    except Exception:
        pass
    return limit


def _dungeon_run_count(cur, service_id: str, player_id: str, dungeon_id: str, dg: Dict[str, Any]) -> Tuple[int, int]:
    today = _utc_today()
    limit = _dungeon_daily_limit(service_id, player_id, dg)
    row = cur.execute(
        """
        SELECT run_count FROM baas_dungeon_daily
        WHERE service_id=? AND player_id=? AND dungeon_id=? AND run_date=?
        """,
        (service_id, player_id, dungeon_id, today),
    ).fetchone()
    done = int(row["run_count"] or 0) if row else 0
    return done, limit


def list_dungeons_status(service_id: str, player_id: str) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    progress = get_progress(service_id, player_id) if feature_enabled(service_id, "pve") else {"stages": []}
    max_cleared = _max_cleared_stage(progress)
    init_db()
    with get_cursor() as cur:
        solo_row = cur.execute(
            "SELECT floor FROM baas_afk_solo_tower WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchone()
    solo_floor = int(solo_row["floor"] or 0) if solo_row else 0
    out = []
    for dg in _economy_cfg(service_id).get("dungeons") or []:
        did = str(dg.get("id") or "")
        with get_cursor() as cur:
            done, limit = _dungeon_run_count(cur, service_id, player_id, did, dg)
        out.append({
            **dg,
            "unlocked": max_cleared >= int(dg.get("unlock_stage") or 0),
            "runs_today": done,
            "daily_limit": limit,
            "max_cleared_stage": max_cleared,
            "solo_tower_floor": solo_floor if did == "solo_tower" else None,
        })
    return {"dungeons": out, "max_cleared_stage": max_cleared, "solo_tower_floor": solo_floor}


def _debit_stamina(cur, service_id: str, player_id: str, cost: int, cfg: Dict[str, Any]) -> None:
    from services.baas.pve_service import _save_stamina, _stamina_state

    stamina = _stamina_state(cur, service_id, player_id, cfg)
    if int(stamina.get("current") or 0) < cost:
        raise ValueError("体力不足")
    stamina["current"] = int(stamina["current"]) - cost
    _save_stamina(cur, service_id, player_id, stamina)


def run_dungeon(
    service_id: str,
    player_id: str,
    dungeon_id: str,
    *,
    team: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    if not feature_enabled(service_id, "economy"):
        raise ValueError("经济/成长系统未启用")
    dg = _dungeon_def(service_id, dungeon_id)
    did = str(dg.get("id") or dungeon_id)
    progress = get_progress(service_id, player_id) if feature_enabled(service_id, "pve") else {"stages": []}
    max_cleared = _max_cleared_stage(progress)
    if max_cleared < int(dg.get("unlock_stage") or 0):
        raise ValueError("推图进度未解锁该副本")
    team_ids = None
    if team and isinstance(team.get("heroes"), list):
        team_ids = [int(x) for x in team["heroes"]]
    power_info = estimate_team_power(service_id, player_id, team_ids=team_ids)
    tp = int(power_info.get("team_power") or 0)
    formulas = _formulas()
    mode = str(dg.get("mode") or "solo")
    init_db()
    with get_cursor() as cur:
        done, limit = _dungeon_run_count(cur, service_id, player_id, did, dg)
        if done >= limit:
            raise ValueError("今日次数已用完")
        entry = str(dg.get("entry_item") or "").strip()
        if entry:
            _consume_item_key(cur, service_id, player_id, entry, 1)
        rewards: Dict[str, Any] = {}
        if mode == "solo_infinite" or did == "solo_tower":
            floor_row = cur.execute(
                "SELECT floor FROM baas_afk_solo_tower WHERE service_id=? AND player_id=?",
                (service_id, player_id),
            ).fetchone()
            floor = int(floor_row["floor"] or 0) + 1 if floor_row else 1
            req = int(500 * eval_formula("tower_power_scale", {"tower_floor": floor}, formulas=formulas))
            if tp < req:
                raise ValueError("战力不足")
            gold = eval_formula("tower_floor_reward", {"tower_floor": floor}, formulas=formulas)
            credit_wallet(cur, service_id, player_id, "gold", gold)
            rewards["gold"] = gold
            now = _now_iso()
            cur.execute(
                """
                INSERT INTO baas_afk_solo_tower (service_id, player_id, floor, updated_at)
                VALUES (?,?,?,?)
                ON CONFLICT(service_id, player_id) DO UPDATE SET floor=excluded.floor, updated_at=excluded.updated_at
                """,
                (service_id, player_id, floor, now),
            )
        else:
            need_stamina = int(dg.get("stamina") or 12)
            if feature_enabled(service_id, "pve"):
                pve_cfg = get_feature_config(service_id, "pve")
                _debit_stamina(cur, service_id, player_id, need_stamina, pve_cfg)
            scale = float(dg.get("power_scale") or 1.0)
            req = int(max_cleared * 8 * scale)
            if tp < int(req * 0.85):
                raise ValueError("战力不足")
            rewards = _grant_rewards(cur, service_id, player_id, dg.get("rewards") or {})
        today = _utc_today()
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_dungeon_daily (service_id, player_id, dungeon_id, run_date, run_count, updated_at)
            VALUES (?,?,?,?,1,?)
            ON CONFLICT(service_id, player_id, dungeon_id, run_date) DO UPDATE SET
                run_count=baas_dungeon_daily.run_count+1, updated_at=excluded.updated_at
            """,
            (service_id, player_id, did, today, now),
        )
    try:
        from services.baas.afk_retention_hooks import on_dungeon_run

        on_dungeon_run(service_id, player_id)
    except Exception:
        pass
    return {
        "dungeon_id": did,
        "rewards": rewards,
        "team_power": tp,
        "runs_today": done + 1,
        "daily_limit": limit,
    }
