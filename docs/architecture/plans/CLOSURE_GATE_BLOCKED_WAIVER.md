# Closure Gate — BLOCKED 平台永久豁免（产品签字）

| 字段 | 值 |
|------|-----|
| 签发日期 | 2026-11-10 |
| 适用范围 | `run_plan_closure_gate.py` / CI `plan closure gate` |
| 决策方 | 产品（用户明确排除下列平台） |

## 豁免项

以下 GAP ID 在 **未解阻前** 不得标为 DONE，但 **允许** CI 与本地门禁使用 `--allow-blocked` 跳过，不阻断主轨合并：

| 平台 / 能力 | 关联 MASTER / Plan ID |
|-------------|------------------------|
| iOS TestFlight / IPA 真发 | `GAP-P2-02-E2E-01`, `C-P1-4`, `GAP-E2E-IOS-01`, `OPEN-2026-11-10-28` |
| 微信小游戏真发 | `GAP-E2E-MG-01`, `GAP-P0-02-S5-01` |

## 约束（解阻前）

1. Capability / UI **不得**暗示上述端已可商业真发（见 `COMM-P0-2` / `COMM-P1-5`）。
2. 本豁免 **不**免除 Wave A 生产库、Secret、多 worker 等 P0 项。
3. 解阻后须从本文件移除对应行，并去掉 CI 对 blocked 项的长期 `--allow-blocked` 依赖（或改为仅 nightly 可选）。

## 复验命令

```bash
cd portals/common/core
py -3 scripts/run_plan_closure_gate.py --allow-blocked
```

证据：`docs/evidence/2026-11-10/OPEN-2026-11-10-03.json`
