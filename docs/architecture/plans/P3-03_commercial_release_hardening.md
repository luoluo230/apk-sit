# P3-03：商业发版缺口收口（排除 iOS / 微信）

| 项 | 值 |
|----|-----|
| 优先级 | P3（承接 P0–P2 假绿与 P1-06 Step3/4） |
| 依赖 | P0-01/02 门禁代码；P1-03 Capability；P1-06 Step1–2；P2-03 通知骨架 |
| Out | iOS/TestFlight、微信小游戏真发、GameServer TypeLoadException 二进制修复（**Annex 永久 Out** 见下） |

### Annex Out — GameServer TypeLoadException（永久，非 Web Portal 范围）

| 项 | 值 |
|----|-----|
| ID | GAP-P3-03-OUT-TYPELOAD |
| 决定 | GameServer 二进制 `TypeLoadException` 修复归属 **game-server / Platform 仓**；apk-site Web Portal **不承接**二进制修补 |
| 本仓 | 保留 DevStack copytree 规避路径；Portal 不声称已修复 IL/程序集加载 |
| 负责人 | Platform / game-server 仓 |
| 跟踪 | [`OPEN_ITEMS_MASTER.md`](./OPEN_ITEMS_MASTER.md) — **DONE（Annex Out）** |
| 证据 | `docs/evidence/2026-11-10/GAP-P3-03-OUT-TYPELOAD.json` |

## Wave 总览

| Wave | 目标 | 验收 |
|------|------|------|
| A | Secret + Postgres 多 worker 证据 | [x] `p3_03_wave_a_prod_evidence.py` → GAP-P0-SEC/DB DONE |
| B | 平台禁 android 回落；渠道三字段单一 helper | [x] `build_grid` + `jenkins_channel_params` 单测 |
| C | sha256 晋级 BLOCK；rollback baseline；灰度快照 | [x] `artifact_identity` + gray snapshots；P1-06 Step3/4 勾选 |
| D | build Journey 302 → 版本四步 | [x] `pages.py` redirect + entrypoint_map |
| E | client×server 对齐矩阵 | [x] `client_server_alignment` + Hub `plane_alignment` |
| F | Android smoke + staging 观测证据 | [x] GAP-E2E-DEV-01 DONE；观测 DONE；服端 deployed DONE |

## 约束

- 一次一个 Wave Step；逻辑进 `services/release/` / `services/build/` 小模块
- 不把 iOS/微信标成可用
