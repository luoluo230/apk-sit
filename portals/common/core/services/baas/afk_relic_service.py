# -*- coding: utf-8 -*-
"""专属神器与装备符文铭刻。解锁跟主线进度走，不在开服一次性放开。"""

from __future__ import annotations

from typing import Any, Dict, List

from models.db import get_cursor, init_db
from services.baas.afk_growth_service import EQUIP_SLOTS, _max_cleared_stage
from services.baas.helpers import _now_iso
from services.baas.pve_service import get_progress
from services.baas.wallet_helpers import debit_wallet

# 前三天先把资源副本和塔打开。符文、神器留到第一周之后，避免第一天把全年内容倒空。
SYSTEM_UNLOCK = {
    "rune_inscribe": 70,
    "artifact": 140,
}

# 装备品质决定可铭刻的孔数，以及能镶进去的最高符文品质。
SOCKETS_BY_EQUIP_QUALITY = {3: 1, 4: 1, 5: 2, 6: 2, 7: 3}

ARTIFACT_LEVEL_SHARD_COST = (15, 25, 40, 60, 90)
ARTIFACT_MAX_LEVEL = len(ARTIFACT_LEVEL_SHARD_COST)


def _bundle() -> Dict[str, Any]:
    from services.baas.afk_config_loader import load_afk_bundle

    data = load_afk_bundle()
    return data if isinstance(data, dict) else {}


def _balance(key: str, default: float) -> float:
    from services.baas.afk_config_loader import balance_number

    return balance_number(key, default)


def _artifact_catalog() -> List[Dict[str, Any]]:
    raw = _bundle().get("artifact_catalog")
    return list(raw) if isinstance(raw, list) and raw else list(_ARTIFACTS)


def _artifact_costs() -> List[int]:
    raw = _bundle().get("artifact_level_shard_cost")
    if isinstance(raw, list) and raw:
        return [int(item) for item in raw]
    return list(ARTIFACT_LEVEL_SHARD_COST)


def _rune_catalog() -> List[Dict[str, Any]]:
    raw = _bundle().get("rune_catalog")
    return list(raw) if isinstance(raw, list) and raw else list(_RUNES)


def _sockets() -> Dict[int, int]:
    raw = _bundle().get("rune_sockets")
    if isinstance(raw, dict) and raw:
        return {int(key): int(value) for key, value in raw.items()}
    return dict(SOCKETS_BY_EQUIP_QUALITY)


def _unlock_stage(key: str) -> int:
    raw = _bundle().get("system_unlock")
    if isinstance(raw, dict) and key in raw:
        return int(raw[key])
    return int(SYSTEM_UNLOCK[key])

_ARTIFACTS: List[Dict[str, Any]] = [
    {"id": "art_01", "hero_id": 1, "name_zh": "破晓战旗", "bonus": "atk", "skill_id": "art_skill_banner", "skill_zh": "开战获得攻击加成"},
    {"id": "art_02", "hero_id": 2, "name_zh": "潮汐圣杯", "bonus": "hp", "skill_id": "art_skill_grail", "skill_zh": "受击后为队友回复生命"},
    {"id": "art_03", "hero_id": 3, "name_zh": "灰烬权杖", "bonus": "atk", "skill_id": "art_skill_ash", "skill_zh": "技能附带灼烧"},
    {"id": "art_04", "hero_id": 4, "name_zh": "北风号角", "bonus": "def", "skill_id": "art_skill_horn", "skill_zh": "开场为前排加护盾"},
    {"id": "art_05", "hero_id": 5, "name_zh": "星陨罗盘", "bonus": "atk", "skill_id": "art_skill_compass", "skill_zh": "暴击时追加一段伤害"},
    {"id": "art_06", "hero_id": 6, "name_zh": "萤火提灯", "bonus": "hp", "skill_id": "art_skill_lantern", "skill_zh": "阵亡时治疗周围队友"},
    {"id": "art_07", "hero_id": 7, "name_zh": "铸铁誓印", "bonus": "def", "skill_id": "art_skill_seal", "skill_zh": "格挡后反震"},
    {"id": "art_08", "hero_id": 8, "name_zh": "暮色竖琴", "bonus": "hp", "skill_id": "art_skill_harp", "skill_zh": "周期性驱散减益"},
    {"id": "art_09", "hero_id": 9, "name_zh": "赤砂弯刀", "bonus": "atk", "skill_id": "art_skill_blade", "skill_zh": "连击提高攻速"},
    {"id": "art_10", "hero_id": 10, "name_zh": "霜纹镜", "bonus": "def", "skill_id": "art_skill_mirror", "skill_zh": "反射部分法术伤害"},
    {"id": "art_11", "hero_id": 11, "name_zh": "古树心核", "bonus": "hp", "skill_id": "art_skill_heart", "skill_zh": "治疗量随神器等级提高"},
    {"id": "art_12", "hero_id": 12, "name_zh": "雷鸣骨笛", "bonus": "atk", "skill_id": "art_skill_flute", "skill_zh": "击杀后获得能量"},
    {"id": "art_13", "hero_id": 13, "name_zh": "沉船锚链", "bonus": "def", "skill_id": "art_skill_anchor", "skill_zh": "控制抗性提高"},
    {"id": "art_14", "hero_id": 14, "name_zh": "月蚀戒指", "bonus": "atk", "skill_id": "art_skill_ring", "skill_zh": "夜战提高暴击伤害"},
    {"id": "art_15", "hero_id": 15, "name_zh": "王城钥匙", "bonus": "hp", "skill_id": "art_skill_key", "skill_zh": "首领战提高生存"},
]

_RUNES: List[Dict[str, Any]] = [
    {"id": "rune_atk", "name_zh": "破军", "stat": "atk", "quality_min": 3},
    {"id": "rune_hp", "name_zh": "长生", "stat": "hp", "quality_min": 3},
    {"id": "rune_def", "name_zh": "磐石", "stat": "def", "quality_min": 3},
    {"id": "rune_crit", "name_zh": "洞悉", "stat": "crit", "quality_min": 5},
    {"id": "rune_haste", "name_zh": "疾风", "stat": "haste", "quality_min": 6},
]


def _cleared(service_id: str, player_id: str) -> int:
    progress = get_progress(service_id, player_id) or {}
    return _max_cleared_stage(progress)


def _require_stage(cleared: int, need: int, label: str) -> None:
    if cleared < need:
        raise ValueError(f"{label}未解锁，需要主线通关 {need} 关（当前 {cleared}）")


def list_systems(service_id: str, player_id: str) -> Dict[str, Any]:
    cleared = _cleared(service_id, player_id)
    return {
        "max_cleared_stage": cleared,
        "systems": [
            {"id": key, "unlock_stage": stage, "unlocked": cleared >= stage}
            for key, stage in (_bundle().get("system_unlock") or SYSTEM_UNLOCK).items()
        ],
    }


def list_artifacts(service_id: str, player_id: str) -> Dict[str, Any]:
    cleared = _cleared(service_id, player_id)
    unlocked = cleared >= _unlock_stage("artifact")
    init_db()
    levels: Dict[str, int] = {}
    if unlocked:
        with get_cursor() as cur:
            rows = cur.execute(
                "SELECT artifact_id, level FROM baas_afk_artifacts WHERE service_id=? AND player_id=?",
                (service_id, player_id),
            ).fetchall()
        levels = {str(r["artifact_id"]): int(r["level"] or 0) for r in rows}
    catalog = []
    costs = _artifact_costs()
    atk_bonus = _balance("artifact_bonus_atk", 18)
    hp_bonus = _balance("artifact_bonus_hp", 90)
    def_bonus = _balance("artifact_bonus_def", 12)
    skill_base = _balance("artifact_skill_power_base", 40)
    skill_step = _balance("artifact_skill_power_per_level", 25)
    for art in _artifact_catalog():
        level = levels.get(art["id"], 0)
        per = atk_bonus if art["bonus"] == "atk" else hp_bonus if art["bonus"] == "hp" else def_bonus
        catalog.append({
            **art,
            "level": level,
            "max_level": len(costs),
            "next_shard_cost": costs[level] if level < len(costs) else 0,
            "bonus_value": int(level * per),
            "skill_power": int(skill_base + level * skill_step),
        })
    return {"unlocked": unlocked, "unlock_stage": _unlock_stage("artifact"), "artifacts": catalog}


def upgrade_artifact(service_id: str, player_id: str, artifact_id: str) -> Dict[str, Any]:
    cleared = _cleared(service_id, player_id)
    _require_stage(cleared, _unlock_stage("artifact"), "专属神器")
    art = next((a for a in _artifact_catalog() if a["id"] == artifact_id), None)
    if art is None:
        raise ValueError("神器不存在")
    init_db()
    with get_cursor() as cur:
        row = cur.execute(
            "SELECT level FROM baas_afk_artifacts WHERE service_id=? AND player_id=? AND artifact_id=?",
            (service_id, player_id, artifact_id),
        ).fetchone()
        level = int(row["level"] or 0) if row else 0
        costs = _artifact_costs()
        if level >= len(costs):
            raise ValueError("神器已满级")
        cost = costs[level]
        from services.baas.afk_growth_service import _consume_item_key

        _consume_item_key(cur, service_id, player_id, "artifact_shard", cost)
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_afk_artifacts (service_id, player_id, artifact_id, level, updated_at)
            VALUES (?,?,?,?,?)
            ON CONFLICT(service_id, player_id, artifact_id) DO UPDATE SET
                level=excluded.level, updated_at=excluded.updated_at
            """,
            (service_id, player_id, artifact_id, level + 1, now),
        )
    return {"artifact_id": artifact_id, "level": level + 1, "shard_cost": cost, "skill_id": art["skill_id"]}


def list_runes(service_id: str, player_id: str) -> Dict[str, Any]:
    cleared = _cleared(service_id, player_id)
    unlocked = cleared >= _unlock_stage("rune_inscribe")
    init_db()
    inscribed: List[Dict[str, Any]] = []
    if unlocked:
        with get_cursor() as cur:
            rows = cur.execute(
                """
                SELECT slot, socket_index, rune_id, rune_quality
                FROM baas_afk_rune_inscriptions WHERE service_id=? AND player_id=?
                """,
                (service_id, player_id),
            ).fetchall()
        inscribed = [dict(r) for r in rows]
    return {
        "unlocked": unlocked,
        "unlock_stage": _unlock_stage("rune_inscribe"),
        "sockets_by_equip_quality": {str(k): v for k, v in _sockets().items()},
        "runes": list(_rune_catalog()),
        "inscribed": inscribed,
    }


def inscribe_rune(service_id: str, player_id: str, slot: str, socket_index: int, rune_id: str, rune_quality: int) -> Dict[str, Any]:
    cleared = _cleared(service_id, player_id)
    _require_stage(cleared, _unlock_stage("rune_inscribe"), "符文铭刻")
    slot_name = str(slot or "").strip()
    if slot_name not in EQUIP_SLOTS:
        raise ValueError("装备槽位无效")
    rune = next((r for r in _rune_catalog() if r["id"] == rune_id), None)
    if rune is None:
        raise ValueError("符文不存在")
    quality = int(rune_quality)
    if quality < int(rune["quality_min"]) or quality > 7:
        raise ValueError("符文品质无效")
    init_db()
    with get_cursor() as cur:
        eq = cur.execute(
            "SELECT quality FROM baas_player_equipment WHERE service_id=? AND player_id=? AND slot=?",
            (service_id, player_id, slot_name),
        ).fetchone()
        equip_quality = int(eq["quality"] or 3) if eq else 3
        sockets = _sockets().get(equip_quality, 1)
        index = int(socket_index)
        if index < 0 or index >= sockets:
            raise ValueError(f"该品质装备只有 {sockets} 个铭刻孔")
        if quality > equip_quality:
            raise ValueError(f"品质 {equip_quality} 的装备不能铭刻品质 {quality} 的符文")
        shard_key = f"rune_shard_q{quality}"
        from services.baas.afk_growth_service import _consume_item_key

        _consume_item_key(cur, service_id, player_id, shard_key, 1)
        debit_wallet(cur, service_id, player_id, "gold", int(_balance("rune_gold_per_quality", 200) * quality))
        now = _now_iso()
        cur.execute(
            """
            INSERT INTO baas_afk_rune_inscriptions
            (service_id, player_id, slot, socket_index, rune_id, rune_quality, updated_at)
            VALUES (?,?,?,?,?,?,?)
            ON CONFLICT(service_id, player_id, slot, socket_index) DO UPDATE SET
                rune_id=excluded.rune_id, rune_quality=excluded.rune_quality, updated_at=excluded.updated_at
            """,
            (service_id, player_id, slot_name, index, rune_id, quality, now),
        )
    return {"slot": slot_name, "socket_index": index, "rune_id": rune_id, "rune_quality": quality}


def power_bonus(service_id: str, player_id: str) -> int:
    bonus = 0
    init_db()
    with get_cursor() as cur:
        arts = cur.execute(
            "SELECT level FROM baas_afk_artifacts WHERE service_id=? AND player_id=? AND level>0",
            (service_id, player_id),
        ).fetchall()
        runes = cur.execute(
            "SELECT rune_quality FROM baas_afk_rune_inscriptions WHERE service_id=? AND player_id=?",
            (service_id, player_id),
        ).fetchall()
    for row in arts:
        bonus += int(_balance("artifact_power_base", 80) + int(row["level"] or 0) * _balance("artifact_power_per_level", 45))
    for row in runes:
        bonus += int(int(row["rune_quality"] or 3) * _balance("rune_power_per_quality", 12))
    return bonus
