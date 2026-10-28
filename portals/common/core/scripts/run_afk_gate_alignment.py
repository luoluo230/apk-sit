#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Gate 战力 vs 推关门槛对齐验收（20/50/80 关 + 成长门槛）。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

CORE = Path(__file__).resolve().parents[1]
if str(CORE) not in sys.path:
    sys.path.insert(0, str(CORE))

OUT = Path(__file__).resolve().parents[4] / "data/afk_shared/afk_gate_alignment_report.json"
CHECK_STAGES = (20, 50, 80)


def main() -> int:
    from services.baas.afk_config_loader import load_afk_bundle, hero_def_map
    from services.baas.afk_power_service import growth_gate_for_stage, hero_power_unified, stage_power_required
    from services.baas.afk_formula_engine import merge_formulas

    bundle = load_afk_bundle() or {}
    formulas = merge_formulas(bundle.get("formulas"))
    heroes = hero_def_map(bundle.get("hero") or bundle)
    hero_list = list(heroes.values())[:5]
    if len(hero_list) < 3:
        print(json.dumps({"ok": False, "error": "hero_defs missing"}))
        return 1

    rows = []
    for stage_num in CHECK_STAGES:
        sid = f"AFK_{(stage_num - 1) // 10 + 1:02d}_{(stage_num - 1) % 10 + 1:02d}"
        required = stage_power_required(sid, formulas=formulas)
        gate = growth_gate_for_stage(sid)
        scenarios = []
        for label, level, star, enhance_avg, talent in (
            ("level_only", 20 + stage_num // 2, 1, 0, 0),
            ("with_star", 25 + stage_num // 3, 3, 0, 5),
            ("full_growth", 35 + stage_num // 2, 4, 6, 10),
        ):
            eq_share = {"atk": int(enhance_avg * 8), "hp": int(enhance_avg * 40), "def": int(enhance_avg * 3)}
            tp = sum(
                hero_power_unified(h, level=level, star=star, talent_points=talent, equip_share=eq_share, formulas=formulas)["power"]
                for h in hero_list[:5]
            )
            win_margin = (tp - required) / max(1, required)
            scenarios.append({
                "profile": label,
                "team_power": tp,
                "required": required,
                "margin_pct": round(win_margin * 100, 1),
                "passes_gate": tp >= required,
                "skillkit_proxy_win": win_margin >= -0.03,
            })
        rows.append({"stage": stage_num, "stage_id": sid, "required_power": required, "growth_gate": gate, "scenarios": scenarios})

    skillkit_note = (
        "SkillKit 精确胜率请在 Unity 运行 AfkLiveServerStage100PlayModeTests；"
        "此处用 unified team_power 与 required 的 margin 作代理指标（margin>=-3% 视为可通）"
    )
    all_pass = all(
        any(s["passes_gate"] for s in r["scenarios"] if s["profile"] == "full_growth")
        for r in rows
    )
    late_gate_ok = all(r["growth_gate"].get("required") == (r["stage"] >= 50) for r in rows)
    report = {
        "test_suite": "afk_gate_alignment",
        "check_stages": list(CHECK_STAGES),
        "rows": rows,
        "skillkit_note": skillkit_note,
        "full_growth_passes_all": all_pass,
        "growth_gate_rules_ok": late_gate_ok,
        "overall_pass": all_pass and late_gate_ok,
    }
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"pass": report["overall_pass"], "report": str(OUT)}, ensure_ascii=False))
    return 0 if report["overall_pass"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
