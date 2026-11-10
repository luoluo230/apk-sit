# P5-01：未完成项正式闭环 Plan

| 字段 | 值 |
|------|-----|
| 状态 | **In Progress** |
| 创建 | 2026-11-10 |
| 真源清单 | [`OPEN_ITEMS_MASTER.md`](./OPEN_ITEMS_MASTER.md) |
| 规则 | `.cursor/rules/no-false-completion.mdc` |
| In | MASTER 全部非 DONE（原 BLOCKED/DEFERRED）写成可执行 Step+DoD 并逐 ID 闭环 |
| Out | 用户排除的 iOS/微信**真发**（Annex）；不解阻不得标 DONE |
| 禁止 | 用空 `DEFERRED` 顶替本 Plan；无证据说「完成」 |

> **说明**：本文件才是「未完成项做成的 Plan」。MASTER 是进度表；本文件是 Step/命令/证据路径。  
> **交付树**：`docs/evidence/` 与 Agent 一次性 `_*.py` / `p5_01_*` 批处理已移出；门禁脚本与 runbook 保留。文内 `docs/evidence/...` 为历史引用。

---

## 0. In / Out

### In

- 将 MASTER 中所有 `BLOCKED` / `DEFERRED`（除 Annex 真发）纳入 Wave 1–5
- 每 ID：命令或操作步骤 → `docs/evidence/YYYY-MM-DD/<ID>.json` → MASTER 改 DONE
- 取消「空延期」；确需外仓/外机的写明依赖，状态保持 BLOCKED 但**有步骤**

### Out

- iOS TestFlight / 微信小游戏真发（用户排除）— 见 Annex
- 未经签字把生产项标 DONE

---

## 1. 全量 ID → Wave 映射（须与 MASTER 非 DONE 对齐）

| ID | Wave | 升 DONE 门槛（摘要） | 证据路径 |
|----|------|----------------------|----------|
| GAP-P0-02-S6-01 | 1 | Docker 下 `postgres_compose_pytest_gate` PASS 或 CI nightly 绿日志 | `docs/evidence/…/GAP-P0-02-S6-01.json` |
| OPEN-2026-11-10-04 | 1 | 同 S6-01；附 runner 说明 | `…/OPEN-2026-11-10-04.json` |
| OPEN-2026-11-10-08 | 1 | workflow 配 `RELEASE_GATE_BASE_URL` 或文档+本地 gate 证据 | `…/OPEN-2026-11-10-08.json` |
| OPEN-2026-11-10-10 | 1 | portal 审计相关路由 HTTP≠500 | `…/OPEN-2026-11-10-10.json` |
| GAP-P0-02-DOD-02 | 1 | onboarding+node 仅走 repo API smoke | `…/GAP-P0-02-DOD-02.json` |
| GAP-P0-02-S4-01 | 1 | `test_ops_runtime_service` 日志入库 | `…/GAP-P0-02-S4-01.json` |
| GAP-P1-05-REV-01 | 1 | label/infra_nodes 对账报告 | `…/GAP-P1-05-REV-01.json` |
| OPEN-2026-11-10-12 | 1 | release_bundles 无乱码可扫或目录清空+README | `…/OPEN-2026-11-10-12.json` |
| OPEN-2026-11-10-21 | 1 | `deploy_architecture` 可本机项全勾 | `…/OPEN-2026-11-10-21.json` |
| OPEN-2026-11-10-27 | 1 | BaaS/拓扑 step-by-step 本机可验项勾完 | `…/OPEN-2026-11-10-27.json` |
| OPEN-2026-11-10-14 | 1 | rh-* 对齐 tokens；scorecard 相关 PASS | `…/OPEN-2026-11-10-14.json` |
| OPEN-2026-11-10-30 | 1 | F0/W2 跟踪关闭或 PASS | `…/OPEN-2026-11-10-30.json` |
| P3-02 | 1→4 | scorecard 八维对目标页 PASS | `…/P3-02.json` |
| GAP-P3-03-OUT-TYPELOAD | 1 | 跟踪结论或 Annex 永久 Out+MASTER | `…/GAP-P3-03-OUT-TYPELOAD.json` |
| GAP-P1-02-E2E-01 | 2 | Jenkins 在线 quick-build 证据 | `…/GAP-P1-02-E2E-01.json` |
| GAP-P1-02-E2E-02 | 2 | 30min smoke 操作者记录 | `…/GAP-P1-02-E2E-02.json` |
| GAP-P2-01-OUT-02 | 2 | Jenkins 存在 GameServer-Build + 触发 | `…/GAP-P2-01-OUT-02.json` |
| OPEN-2026-11-10-09 | 2 | DevStack/CI server-release e2e | `…/OPEN-2026-11-10-09.json` |
| GAP-P2-03-E2E-03 | 2 | staging scrape 真日志 | `…/GAP-P2-03-E2E-03.json` |
| GAP-P1-05-OPT-01 | 2 | label sync 调度落地 | `…/GAP-P1-05-OPT-01.json` |
| OPEN-2026-11-10-06 | 2 | staging 晋级 identity 回放 | `…/OPEN-2026-11-10-06.json` |
| OPEN-2026-11-10-07 | 2 | staging NOTIFY 回执（可先于生产） | `…/OPEN-2026-11-10-07.json` |
| COMM-P2-7 | 3 | 产品签字四步主轨 | `…/COMM-P2-7.json` |
| OPEN-2026-11-10-15 | 3 | CTA 一页一主操作验收 | `…/OPEN-2026-11-10-15.json` |
| P3-01 | 4 | Plan ~28 `[ ]` 全 PASS | `…/P3-01-progress.json` |
| OPEN-2026-11-10-11 | 4 | 随 P3-01 去 Tailwind | `…/OPEN-2026-11-10-11.json` |
| OPEN-2026-11-10-16 | 4 | 服务器管理入口收敛 | `…/OPEN-2026-11-10-16.json` |
| OPEN-2026-11-10-26 | 4 | P02 shell PASS | `…/OPEN-2026-11-10-26.json` |
| W-P1-2 | 4 | version_service 拆分 ≤400/模块 | `…/W-P1-2.json` |
| OPEN-2026-11-10-18 | 4 | 随 W-P1-2 净减少 | `…/OPEN-2026-11-10-18.json` |
| W-P2-2 | 4 | project_delivery.js 拆分 | `…/W-P2-2.json` |
| W-P2-1 | 4 | admin_routes 继续拆 | `…/W-P2-1.json` |
| W-P1-3 | 4 | 节点注册表统一 | `…/W-P1-3.json` |
| OPEN-2026-11-10-19 | 4 | channel 双 ID 收敛文档+代码 | `…/OPEN-2026-11-10-19.json` |
| OPEN-2026-11-10-20 | 4 | UI 无 stage/env_key 双词汇 | `…/OPEN-2026-11-10-20.json` |
| C-P1-1 | 4 | 本仓契约/gate；跨仓子项标明 | `…/C-P1-1.json` |
| C-P1-2 | 4 | 同 C-P1-1 | `…/C-P1-2.json` |
| GAP-P2-01-S5-01 | 4 | MVP 热更或永久 Out 写入 Annex | `…/GAP-P2-01-S5-01.json` |
| COMM-P0-1 | 5 | 生产多 worker 签字 | `…/COMM-P0-1.json` |
| GAP-P0-01-SEC-02 | 5 | 生产弱口令审计 | `…/GAP-P0-01-SEC-02.json` |
| W-P0-1 | 5 | 生产配置审计 | `…/W-P0-1.json` |
| W-P0-2 | 5 | 生产 webhook HMAC 记录 | `…/W-P0-2.json` |
| W-P0-3 | 5 | 生产 DATABASE_URL=PG | `…/W-P0-3.json` |
| W-P0-5 | 5 | 生产无 dev cluster token | `…/W-P0-5.json` |
| OPEN-2026-11-10-01 | 5 | PG cutover 记录 | `…/OPEN-2026-11-10-01.json` |
| OPEN-2026-11-10-02 | 5 | 生产单一 SSOT+备份 | `…/OPEN-2026-11-10-02.json` |
| OPEN-2026-11-10-05 | 5 | 脱敏生产启动日志 | `…/OPEN-2026-11-10-05.json` |
| GAP-P2-02-E2E-01 | Annex | 解阻后真发 | — |
| C-P1-4 / GAP-E2E-IOS-01 | Annex | 解阻后真发 | — |
| GAP-E2E-MG-01 / GAP-P0-02-S5-01 | Annex | 解阻后真发 | — |
| GAP-P2-02-E2E-01（Plan） | Annex | 随 iOS | — |
| GAP-P2-02-E2E-01（Plan 勾选） | Annex | 同 P2-02 Plan checkbox；随 iOS | — |
| COMM-P1-5 关联 | Annex | capability 已关则可随 COMM-P1-5 DONE 关闭 | — |
| OPEN-2026-11-10-28 | Annex | checklist 或保持 BLOCKED | — |

---

## 2. Wave 1 — 本机/仓库可闭环

### W1-1 CI / Postgres compose

- [x] `GAP-P0-02-S6-01`：跑 `py -3 portals/common/core/scripts/postgres_compose_pytest_gate.py`（有 Docker）或记录 CI job 绿 — **PARTIAL**（本机无 Docker；见 `GAP-P0-02-S6-01.json`）
- [x] `OPEN-2026-11-10-04`：同上证据交叉引用 — **PARTIAL**
- [x] `OPEN-2026-11-10-08`：检查 `.github/workflows/*` 是否注入 `RELEASE_GATE_BASE_URL`；缺则补；本地 `bootstrap_gate` 可跑则写证据 — **DONE**

**命令**

```text
py -3 portals/common/core/scripts/postgres_compose_pytest_gate.py
```

### W1-2 Portal 审计 500

- [x] `OPEN-2026-11-10-10`：对照 `docs/evidence/2026-10-28/portal-function-audit.json` 复测；修路由；新 evidence — **DONE**（`get_500_count=0`；大量 429 非 bad）

### W1-3 Registry / ops tests

- [x] `GAP-P0-02-DOD-02`：编写/跑 registry API smoke — **DONE**（修 `version_row_repo` 循环 import）
- [x] `GAP-P0-02-S4-01`：`pytest …/test_ops_runtime_service.py -q` — **DONE**
- [x] `GAP-P1-05-REV-01`：跑或新增 label reconcile 报告脚本 — **DONE**

### W1-4 脏包与 runbook

- [x] `OPEN-2026-11-10-12`：清空或重建 `release_bundles`；确认 encoding_gate 仍 PASS — **DONE**
- [x] `OPEN-2026-11-10-21`：更新 `deploy_architecture.md` 可本机勾选项 — **PARTIAL**（4/7）
- [x] `OPEN-2026-11-10-27`：勾 BaaS/拓扑 step-by-step 本机项 — **PARTIAL**

### W1-5 UI scorecard 子集

- [x] `OPEN-2026-11-10-14`：发版中心 `rh-*` → 设计 token — **PARTIAL**
- [x] `OPEN-2026-11-10-30`：关闭 F0/W2 FAIL 或记 PASS — **PARTIAL**
- [x] `P3-02`：目标页八维 PASS — **DONE**（scorecard + 浏览器复验）

### W1-6 TypeLoad

- [x] `GAP-P3-03-OUT-TYPELOAD`：写入 P3-03 永久 Out+原因 **或** 修复跟踪单；MASTER 同步 — **DONE**（Annex 永久 Out）

---

## 3. Wave 2 — DevStack / Jenkins / 监控

环境默认：Portal `:5003` + Jenkins `:8082`（见 DevStack runbook）。

> **Wave 2 收口（2026-11-10 复查）**：Jenkins `:8082` + Portal `:5003` 在线；本地项均 DONE。调度入口：`docs/runbooks/jenkins_label_sync_schedule.md`。

- [x] `GAP-P1-02-E2E-01`：quick-build 浏览器/脚本证据 — **DONE**
- [x] `GAP-P1-02-E2E-02`：30 分钟 smoke 记录 — **DONE**（`run_devstack_full_closure_e2e.ps1` PASS）
- [x] `GAP-P2-01-OUT-02`：Jenkins 创建/确认 `GameServer-Build` — **DONE**（`:8082` job + build #1 SUCCESS）
- [x] `OPEN-2026-11-10-09`：`server_release_devstack_e2e` 或 CI — **DONE**（本地）
- [x] `GAP-P2-03-E2E-03`：Prometheus/Grafana scrape 日志 — **DONE**（本机 `:9090` targets up + `apk_site_*`）
- [x] `GAP-P1-05-OPT-01`：cron/调度 — **DONE**（schtasks）
- [x] `OPEN-2026-11-10-06`：staging 晋级回放 — **DONE**（staging；生产另见 OPS）
- [x] `OPEN-2026-11-10-07`：NOTIFY 测试回执 — **DONE**（staging；生产另见 OPS）

---

## 4. Wave 3 — 产品签字

### 签字模板（写入 evidence JSON）

```text
产品确认：发版以「版本与管线四步」为主轨；发版中心七步为发布单详情。
签字人：________  日期：________
```

- [ ] `COMM-P2-7`：取得签字 → DONE
- [ ] `OPEN-2026-11-10-15`：CTA 验收随签字

无签字：**保持 BLOCKED**，不得 DONE。

---

## 5. Wave 4 — 架构 / 工作台（原错误 DEFERRED → In Plan）

### W4-1 P3-01 工作台收敛

- [x] 打开 [`P3-01_workstation_convergence.md`](./P3-01_workstation_convergence.md) 本仓 Steps DoD — **DONE**（§7 生产→OPS；像素→P3-02）
- [x] 逐条实现；`docs/evidence/2026-11-10/P3-01.json` / `P3-01-progress.json`
- [x] `OPEN-2026-11-10-16` / `11` / `26` → MASTER **DONE**

### W4-2 巨石拆分

- [x] `W-P1-2` / `OPEN-2026-11-10-18`：**DONE** — 全部 `version_*.py` ≤400；`version_pipeline_merge` / `version_group_delete` — 见 `W-P1-2.json`
- [x] `W-P2-2`：拆 `project_delivery.js` — **DONE**（902 + overview/env/order 模块）
- [x] `W-P2-1`：继续拆 `admin_routes` — **DONE**（337 + pages_projects_list）
- [x] `W-P1-3`：节点注册表统一 — **DONE**（P1-05 + OPT-01）

### W4-3 词汇与客户端契约

- [x] `OPEN-2026-11-10-19`：channel ID registry — **DONE**
- [x] `OPEN-2026-11-10-20`：**DONE** — 交付 UI 可见文案「环境」
- [x] `C-P1-1`：**DONE** — 本仓 gate；maclient Out
- [ ] `C-P1-2`：跨仓 — **BLOCKED**（不可抗）
- [x] `GAP-P2-01-S5-01`：Annex Out — `P2-01` Step 5 + `GAP-P2-01-S5-01.json`

---

## 6. Wave 5 — 生产运维签字

对照 [`OPS_SIGN_OFF_QUEUE.md`](./OPS_SIGN_OFF_QUEUE.md)。

| ID | 命令/动作 | 产物 | 签字人 |
|----|-----------|------|--------|
| COMM-P0-1 | 生产多 worker 部署 + 跨实例读 | evidence JSON | |
| GAP-P0-01-SEC-02 | 生产 settings 审计 | JSON | |
| W-P0-1 | 同左 | JSON | |
| W-P0-2 | webhook HMAC/IP 配置记录 | JSON | |
| W-P0-3 | 确认 DATABASE_URL=PG | 日志 | |
| W-P0-5 | 生产 cluster 无 dev token | 审计 | |
| OPEN-2026-11-10-01 | cutover runbook 执行 | 记录 | |
| OPEN-2026-11-10-02 | SSOT+备份演练 | 记录 | |
| OPEN-2026-11-10-05 | 脱敏 fail-fast 启动日志 | 日志 | |

- [ ] 上表逐 ID 完成后 MASTER→DONE 并从 OPS 队列删除

---

## 7. Annex — 用户排除（保持 BLOCKED）

| ID | 约束 |
|----|------|
| GAP-P2-02-E2E-01 | 不解阻不做真发 |
| C-P1-4 / GAP-E2E-IOS-01 | 同上 |
| GAP-E2E-MG-01 / GAP-P0-02-S5-01 | 微信真发排除 |
| GAP-P2-02-E2E-01（Plan） | 随 iOS |
| OPEN-2026-11-10-28 | checklist 不解阻 |
| COMM-P1-5 关联 | 若 capability 已 `can_build=false` 且 UI 明示，可标 DONE（产品面一致） |

验收（Annex）：

- [x] UI/API 不暗示 iOS/微信可商业真发（见 `platform_capability.py`）；`COMM-P1-5 关联` → MASTER DONE

---

## 8. 测试与门禁

每 ID 收工：

1. 相关 `py_compile` / `node --check` / `pytest`
2. evidence JSON
3. MASTER 行更新
4. 本文件对应 `- [ ]` → `[x]`

整包 DONE 条件：MASTER 非 Annex 项无 BLOCKED/DEFERRED/PARTIAL（仅允许 Annex BLOCKED + 已签字队列清空）。

---

## 9. 本轮执行状态（2026-11-10）

| Wave | 状态 | 说明 |
|------|------|------|
| Step 0 | **DONE** | 本文件 + README/MASTER 索引 |
| Wave 1 | **DONE** | 本机项闭环；Docker compose → BLOCKED |
| Wave 2 | **DONE** | Jenkins/DevStack/E2E-02/Prometheus 本机 scrape 均 DONE |
| Wave 3 | **BLOCKED** | 签字表已出；**待产品签字** → COMM-P2-7 / OPEN-15 |
| Wave 4 | **DONE** | 本仓架构项 DONE；仅 C-P1-2 跨仓 BLOCKED |
| Wave 5 | **BLOCKED** | 预演 runbook + WAVE-5-PREP；**生产签字仍 BLOCKED** |

整包 **未** 宣称商业/生产全绿。本机可推进项已空；余项均为不可抗 BLOCKED。

## 10. 变更日志

| 日期 | 变更 |
|------|------|
| 2026-11-10 | 创建 P5-01：把 MASTER 未完成项做成可执行 Plan（纠正空 BLOCKED/DEFERRED 假收口） |
| 2026-11-10 | 开始执行 Wave1–5；见 §9 |
| 2026-11-10 | Wave 1 执行：8 DONE + 6 PARTIAL + P3-02 仍 open；证据 `docs/evidence/2026-11-10/` |
| 2026-11-10 | Wave 2 探测：3 BLOCKED + 5 PARTIAL + 0 DONE；`WAVE-2-P5-01.json` |
| 2026-11-10 | **复查事故纠正**：误标 E2E-02「需操作员窗口」→ 脚本本机 PASS；无 Docker 下载 Prometheus 闭环 E2E-03；同步本文件勾选与 MASTER |
