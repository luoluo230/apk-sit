# Plan DoD + 评审 W/C Closure — 缺口真源清单

> **标准（用户要求，不可降级）**：`P0-01`～`P2-03` 每个 Plan 的 DoD 与 Step 验收 **100% 勾完且可复验**；`full_stack_expert_review.md` 中 W/C 项 **有证据 closure**；**线上可用** — 不是「代码 merge 了就行」。
>
> **更新时间**：2026-07-29（strict pass #2）  
> **代码基线**：`newVersion` 分支  
> **结论**：**未达标（除 iOS 硬阻塞外）**。Evidence JSON 可标 `DONE`，但 **严格 Plan DoD** 仍有多项 OPEN — 见 §1.5。

---

## 1.5 严格审计 vs Evidence JSON（2026-07-29）

| 维度 | Evidence gate | 严格 DoD | 说明 |
|------|---------------|----------|------|
| Master gate | `run_plan_closure_gate.py --allow-blocked` → PASS | 无 `--allow-blocked` 时 iOS 2 项 BLOCKED | iOS 可接受阻塞 |
| CI 接入 | `production_secret_gate` + `plan_closure_gate` 已入 workflow | `postgres_compose` nightly 仍 `SKIP_POSTGRES_COMPOSE=1`（无 Docker runner） | PG 全链路未 CI 证明 |
| admin_routes | **447 行** ≤800 | W-P2-1 **PARTIAL DONE** — 已拆 search + project workspace | `pages_search.py`、`pages_project_workspace.py` |
| version_service | evidence 可 DONE | **1304 行**，目标 ≤400/模块 **OPEN** | Wave6 未完成 |
| DevStack E2E | 脚本存在 | 需 Portal :5003 live + Jenkins | **OPEN** |
| Server release E2E | mock enqueue 证据 | 真实 Agent 回调 **OPEN** | Wave4 |
| P2-03 notify | local capture + mock | staging live release_order **OPEN** | Wave5 |
| Postgres | `db_factory` + migrate dry-run | `db.py` 仍 SQLite 真源；`init_db` 仅校验 psycopg2 | **PARTIAL** |
| maclient C-P1-1/2/3 | bootstrap 文档 | 代码 + hotupdate impl **OPEN** | 跨仓 |

**除 iOS（GAP-P2-02-E2E-01、C-P1-4）外，其余 GAP 尚未 100% 严格 closure。**

## 0. 为什么「半成品」比没做更危险

| 现象 | 后果 |
|------|------|
| Plan 标 `[x]`，实际只有单测/mock | 线上挂了以为「这块做完了」，排查从错误假设开始 |
| Portal MVP 有 UI/API，Agent/管线未 E2E | 按钮能点、Job 入队，但服没起来 — 卡在中间层 |
| SQLite + 单 worker 假设未写进部署文档 | 多 worker 部署后项目/发布单数据不一致，难复现 |
| 通知/回滚代码在，`.env` 未配 | verify 失败静默，无 webhook、无 rollback |
| 18 平台 UI vs 3 条 Jenkins Job | 运营误点不可构建平台，错误信息不在同一层 |

**本文件用途**：任何「做完了吗？」「线上 X 挂了从哪查？」—— **只认本文 + 对应 runbook**，不认 Plan 里的 `[x]`。

---

## 1. 总览

| 维度 | 数量 | 说明 |
|------|------|------|
| Plan 文档显式 `[ ]` | **18 项** | §3 — 部分已在代码/evidence 落地，**严格状态见 §1.5** |
| 评审 W/C 项 | **16 项** | 见 §4；evidence 在 `docs/evidence/2026-07-29/` |
| iOS 硬阻塞 | **2 项** | GAP-P2-02-E2E-01、C-P1-4 — `ios_provisioning_checklist.md` |
| Master gate | **PASS（--allow-blocked）** | CI 已接入；严格无 flag 仍因 iOS BLOCKED |

**Evidence 目录**：[`docs/evidence/2026-07-29/`](../../evidence/2026-07-29/)

---

## 2. 生产阻断项（优先级序）

| 优先级 | ID | 缺口 | 不 closure 线上会怎样 |
|--------|-----|------|------------------------|
| P0 | GAP-P0-SEC-01 | 生产 Secret 未在真实环境注入并 fail-fast 验证 | 弱凭据、webhook 裸奔 |
| P0 | GAP-P0-DB-01 | 仍 SQLite 真源；PostgreSQL 轨未落地 | 多 worker/高并发数据损坏 |
| P0 | GAP-P0-DB-02 | 多 worker 读写未手工/E2E 验证 | A 写 B 读不到，发布单状态漂移 |
| P0 | GAP-P0-OPS-01 | 部署模式（单 worker vs 多 worker）未文档化决策 | 运维按错误假设扩容 |
| P1 | GAP-E2E-DEV-01 | DevStack 全链路未 smoke（onboard → build → publish → bootstrap） | Dev 日常发版路径不确定 |
| P1 | GAP-E2E-SRV-01 | P2-01 Server Release DevStack E2E 未跑通 | 客户端发了、服没更 |
| P1 | GAP-E2E-IOS-01 | macOS Jenkins iOS → IPA → TestFlight 未 E2E | iOS 签名/UI 全是空壳 |
| P1 | GAP-E2E-OBS-01 | P2-03 通知/自动回滚仅 mock 单测 | staging verify 失败无人知、不回滚 |
| P2 | GAP-E2E-MG-01 | wechat_minigame 端到端 publish 未验证 | 小游戏渠道发版不可信 |

---

## 3. Plan 显式未完成项（文档 `[ ]` 真源）

### P0-01 — 生产安全加固

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P0-01-DOD-01 | DoD: W-P0-1/2/5 issue closure | **NOT_DONE** | 无 GitHub issue 链接 | `docs/architecture/plans/P0-01_*.md` §6 |
| GAP-P0-01-CI-01 | §4 CI `production_secret_gate` | **DONE** | 已接入 `.github/workflows/release-platform-gate.yml` + `plan_closure_gate` | CI 配置 |
| GAP-P0-01-SEC-02 | Step 2 验收隐含 | **PARTIAL** | gate 已扫 `.json`；本地 dev `settings.json` gitignore | `config/settings.json`、`production_secret_gate.py` |

### P0-02 — Config Registry

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P0-02-PRE-01 | 前置：DB/JSON 备份 | **NOT_DONE** | 无运维签字备份记录 | `data/apk_site.db` |
| GAP-P0-02-PRE-02 | 前置：部署模式决策 | **NOT_DONE** | 无 `docs/runbooks/deployment_topology.md` 类文档 | P0-02 §3 |
| GAP-P0-02-S2-01 | Step 2: 进程 A 写 B 读 | **NOT_DONE** | 仅 `test_project_repo_concurrency.py` 双线程 | `repositories/registry/`、`models/db.py` |
| GAP-P0-02-S3-01 | Step 3: 10 thread release_order stress | **NOT_DONE** | 无专项测试/script | `models/db.py` release_orders 表 |
| GAP-P0-02-S4-01 | Step 4: test_ops_runtime_service | **PARTIAL** | 2026-07-29 本地 `3 passed`；Plan 仍标环境依赖 | `tests/test_ops_runtime_service.py` |
| GAP-P0-02-S5-01 | Step 5: wechat_minigame E2E publish | **NOT_DONE** | scope 单测有，无 publish E2E | `scope_resolver.py`、Jenkins minigame job |
| GAP-P0-02-S6-01 | Step 6: compose pytest 全 pass | **PARTIAL** | `postgres_compose_pytest_gate.py` + CI nightly（`SKIP_POSTGRES_COMPOSE=1` 回退 sqlite pytest）；**db.py 仍 SQLite** | `docker-compose.postgres-test.yml` |
| GAP-P0-02-S6-02 | Step 6: migrate script | **DONE（dry-run）** | `migrate_sqlite_to_postgres.py` 存在；生产 apply 未签字 | `docs/runbooks/postgres_migration.md` |
| GAP-P0-02-DOD-01 | DoD: backup runbook 含 DB SSOT | **NOT_DONE** | `production_backup_restore.md` 有路径，**缺「DB 单一真源 / mirror 关系」专节** | `docs/runbooks/production_backup_restore.md` |
| GAP-P0-02-DOD-02 | DoD: P1-02/P1-05 可依赖 repo API | **PARTIAL** | API 存在，**无跨 Plan 集成 smoke 签字** | `repositories/registry/accessors.py` |

### P1-01 — Ops helpers 拆分

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P1-01-DOD-01 | DoD: W-P1-1 关闭 | **NOT_DONE** | helpers 已拆（192 行），**无正式评审 closure** | `services/ops/helpers.py` + 6 子模块 |
| GAP-P1-01-DOC-01 | Step 6: entrypoint_map 更新 | **NOT_DONE** | `entrypoint_map.md` 存在，Ops 模块图未对齐拆分后结构 | `docs/architecture/entrypoint_map.md` |
| GAP-P1-01-DUP | 文档重复 DoD §6/§7 | **DOC_DEBT** | 第二段 DoD 仍 `[ ]`，与第一段 `[x]` 矛盾 — **以第一段+代码为准** | Plan 文档本身 |

> **注**：P1-01 代码拆分已完成（helpers 192 行）；缺口在 **评审 closure + 文档同步**，不是回退拆分。

### P1-02 — Onboarding

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P1-02-E2E-01 | Step 3: Browser E2E quick-build | **NOT_DONE** | 需 Jenkins 在线；无 CI/签字记录 | `docs/runbooks/project_onboarding.md` |
| GAP-P1-02-E2E-02 | Step 4: 新 clone 30min smoke | **NOT_DONE** | 无记录 | `Start-DevStack.ps1`、onboarding API |

### P1-03 — Platform Capability

| Plan DoD | 状态 |
|----------|------|
| 全部 `[x]` | **DONE（代码）** — W-P2-3 在 Plan 内标关闭；见 §4 评审表 |

### P1-04 — Dev 交付简化

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P1-04-E2E-01 | Step 1: 真实 DevStack ensure runtime | **NOT_DONE** | 仅 mock 单测 | `runtime_ensure_service.py`、`Invoke-DevQuickPublish.ps1` |
| GAP-P1-04-REV-01 | DoD: W-P1-4 关闭 | **FALSE_GREEN** | Plan 标 `[x]`；**无 DevStack E2E 证据** | `precheck_release_order` dev 路径 |

### P1-05 — Node Registry

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P1-05-OPT-01 | Step 4: Jenkins label 对账 Cron | **DEFERRED ⏸** | 明确留待后续 | `jenkins_manager.py` |
| GAP-P1-05-REV-01 | DoD: W-P1-3/W-P2-4 | **PARTIAL** | infra_nodes 已入库；Jenkins 对账未做 | `repositories/infra_nodes_repo.py` |

### P2-01 — Server Release Plane

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P2-01-E2E-01 | DoD: DevStack E2E demo | **NOT_DONE** | Portal MVP + mock enqueue；**Agent 回调链未 DevStack 证明** | `server_deploy_dispatch.py`、`tools/gameserver_agent_exec.py` |
| GAP-P2-01-OUT-01 | Out: game-server Agent 完整实现 | **NOT_DONE** | `tools/gameserver_agent_exec.py` 有 stub；**maclient/game-server 生产 Agent 未对齐** | game-server 仓库 |
| GAP-P2-01-OUT-02 | Out: Jenkins GameServer-Build | **NOT_DONE** | 无 job | jenkins-clone |
| GAP-P2-01-S5-01 | Step 5: config 热更 | **DEFERRED ⏸** | — | — |
| GAP-P2-01-REV-01 | 评审 §5.2 服务端发布 gap | **PARTIAL** | Portal 侧 gate 有；**自动部署服未闭环** | `precheck_release_order` server gate |

### P2-02 — Client Bootstrap

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P2-02-E2E-01 | Step 5: macOS iOS job → ipa + TestFlight | **NOT_DONE** | 管线脚本有；**无 macOS agent + 证书 E2E** | `commercial_ios_pipeline.sh`、`ios_production_signing.md` |
| GAP-P2-02-OUT-01 | Out: WebGL/小游戏热更 | **NOT_DONE** | 无 Plan | maclient |

### P2-03 — 观测事故闭环

| ID | Plan 位置 | 状态 | 验证命令 / 证据 | 出问题时查 |
|----|-----------|------|-----------------|------------|
| GAP-P2-03-E2E-01 | Step 1: 模拟 verify fail → webhook 收 payload | **FALSE_GREEN** | Plan `[x]`；**仅 mock 单测** `test_observability_incident_loop.py` | `outbound_webhook.py` |
| GAP-P2-03-E2E-02 | Step 2: staging auto-rollback E2E | **FALSE_GREEN** | Plan `[x]`；rollback **mock**，无真实 release_order 链 | `incident_loop_service.py` |
| GAP-P2-03-E2E-03 | Step 3: Prometheus docker scrape | **FALSE_GREEN** | Plan `[x]`；**无 CI/docker 抓取记录** | `docs/grafana/README.md`、`grafana_smoke_gate.py` |
| GAP-P2-03-OPS-01 | DoD: notify 生产可用 | **NOT_DONE** | 代码有；**`NOTIFY_WEBHOOK_URL` 生产未配未验** | `.env`、`incident_release_rollback.md` |

---

## 4. 评审 W/C 项 closure 表

> 来源：`docs/architecture/full_stack_expert_review.md` §3.3、§4.1  
> **Closure 定义**：代码 + 线上/E2E 证据 + issue/本文 ID 更新 — 三者缺一即 **OPEN**。

### Web 端（W-P）

| ID | 问题摘要 | Closure 状态 | 证据 / 缺口 | 排查入口 |
|----|----------|--------------|-------------|----------|
| W-P0-1 | 默认弱凭据 | **PARTIAL** | `config.py` 无硬编码默认；**`settings.json` 仍有 admin123**；dev Jenkins 仍可能用弱口令 | `config.py`、`settings.json`、`jenkins_manager.py` |
| W-P0-2 | CSRF 大面积豁免 | **DONE（代码）** | internal HMAC + IP；delivery JSON 仍要 CSRF — **生产 env 未签字** | `app_new.py`、`webhook_auth.py` |
| W-P0-3 | SQLite 单点 | **OPEN** | thread-local 已做；**仍 SQLite 真源，无 Postgres 迁移** | `models/db.py`、`postgres_migration.md` |
| W-P0-4 | 多 worker 不一致 | **PARTIAL** | DB proxy 已做；**A 写 B 读、stress 未验** | `repositories/registry/_proxies.py` |
| W-P0-5 | cluster relay dev token | **PARTIAL** | env 注入已实现；**`Start-DevStack.ps1` 仍写 `ma-cluster-relay-dev`**；game-server `cluster.json` 在 maclient 仓 | `Start-DevStack.ps1`、game-server 仓 |
| W-P1-1 | Ops 巨石 | **DONE（代码）** | helpers **192 行**；**评审未 formal close** | `services/ops/*.py` |
| W-P1-2 | version_service 巨石 | **OPEN** | **1916 行**，无拆分 Plan | `services/admin/version_service.py` |
| W-P1-3 | 三套节点 registry | **PARTIAL** | P1-05 infra_nodes；**Jenkins 对账 ⏸** | `infra_nodes_repo.py` |
| W-P1-4 | Publish 硬依赖 Runtime | **PARTIAL** | P1-04 dev auto-ensure；**DevStack E2E 未验** | `runtime_ensure_service.py` |
| W-P1-5 | 文档自评 gap | **OPEN** | gap_analysis 35/35 ≠ 本清单 closure | 本文 |
| W-P2-1 | admin_routes 大 | **PARTIAL DONE** | **447 行**（拆至 `pages_search.py`、`pages_project_workspace.py`）；size gate PASS | `routes/admin_routes.py` |
| W-P2-2 | 前端 JS 大 | **OPEN** | `project_delivery.js` **2076 行** | `static/project_*.js` |
| W-P2-3 | 平台无 capability badge | **DONE（代码）** | P1-03 | `platform_capability.py` |
| W-P2-4 | build_nodes 不在 backup | **DONE（代码）** | infra_nodes 在 apk_site.db | P1-05 |

### 客户端（C-P）

| ID | 问题摘要 | Closure 状态 | 证据 / 缺口 | 排查入口 |
|----|----------|--------------|-------------|----------|
| C-P1-1 | 三路径并存 | **PARTIAL** | 生产无 OSS silent fallback；**DEVELOPMENT 仍可有 legacy** | maclient `Main.cs` |
| C-P1-2 | 配置真源分散 | **PARTIAL** | 文档 v2 + checksum 脚本；**手工改 asset 仍可能** | `client_bootstrap_contract.md` |
| C-P1-3 | WebGL/小游戏热更 | **OPEN** | **无 Plan、无实现** | — |
| C-P1-4 | iOS 生产签名 | **PARTIAL** | Portal wizard + pipeline env；**无 macOS E2E** | `platform_signing_service.py`、maclient |

### 评审 §9.2「不要做的事」违反情况

| 条款 | 现状 |
|------|------|
| 不要继续堆 version_service | **违反** — 1916 行且 P2-02 继续改 |
| 不要扩 18 平台都可构建 | **已缓解** — P1-03 capability gate |
| 不要把 Ops 塞回 Delivery | **未违反** |

---

## 5. 假绿清单（Plan 标 `[x]` 但缺线上/E2E 证据）

| Plan | 声称完成项 | 实际 | 必须补的证据 |
|------|------------|------|--------------|
| P0-01 | Step 1–6 全 `[x]` | CI gate 未接入；settings.json 弱口令 | CI 绿 + 生产 env 启动 fail-fast 日志 |
| P0-02 | Step 1–5 核心 `[x]` | Postgres 轨 skeleton only | compose + migrate + pytest on PG |
| P1-04 | DoD 全 `[x]`、W-P1-4 关闭 | 无 DevStack ensure smoke | `Invoke-DevQuickPublish.ps1` 真实跑通记录 |
| P2-01 | Portal MVP `[x]` | 无 DevStack deploy 回调 | server release runbook E2E 签字 |
| P2-02 | DoD 全 `[x]`、C-P1-1/2 关闭 | iOS E2E 缺；C-P1-4 仅 runbook | TestFlight 上传截图/日志 |
| P2-03 | Step 1–3 全 `[x]` | webhook/rollback/scrape 仅 mock | staging 故意 verify fail → 飞书/钉钉收到 |
| P2-03 | DoD notify 生产可用 | NOTIFY_* 未生产配置 | 生产 `.env` 脱敏配置记录 + 测试事件 |

---

## 6. 按症状排查 — 线上出问题从哪入手

| 症状 | 先查（优先级） | 常见根因（当前缺口） |
|------|----------------|----------------------|
| 多 worker 下项目/版本数据不一致 | `repositories/registry/`、`SAVE_JSON_MIRROR`、是否单 worker | **GAP-P0-02-S2-01** 未验 |
| Jenkins webhook 401/发布单不更新 | `webhook_auth.py`、`JENKINS_WEBHOOK_SECRET`、internal IP | P0-01 Secret 未配 |
| Dev precheck「Runtime 未启动」 | `runtime_ensure_service.py`、Agent 是否在线 | **GAP-P1-04-E2E-01** |
| Prod publish 失败 | `order_publish_flow.py`、active runtime、precheck | W-P1-4 设计如此 |
| verify 失败无告警 | `NOTIFY_WEBHOOK_URL`、`outbound_webhook.py` | **GAP-P2-03-OPS-01** |
| staging verify 失败未回滚 | `release_policy_service` staging 默认、`incident_loop_service` | **GAP-P2-03-E2E-02** |
| 客户端 bootstrap 失败 | `/api/public/runtime-bootstrap`、bundle active | P2-02 路径 |
| iOS 构建/签名失败 | `IOS_SIGNING_JSON`、Jenkins credentials、macOS agent | **GAP-P2-02-E2E-01** |
| 客户端发了服没更 | server release gate、`deploy_server_artifact` job | **GAP-P2-01-E2E-01** |
| 小游戏渠道 publish 异常 | scope wechat_minigame、Jenkins job | **GAP-P0-02-S5-01** |
| 备份恢复后数据缺 | `production_backup_restore.md`、是否只恢复了 JSON 未恢复 db | **GAP-P0-02-DOD-01** |
| CI 过了线上仍挂 | `.github/workflows/release-platform-gate.yml` 不覆盖 secret gate / PG / notify | §7 |

---

## 7. CI / 门禁 vs 线上差距

| 门禁 | 在 CI 中？ | 覆盖缺口？ |
|------|------------|------------|
| pytest 全量 | ✅ `release-platform-gate.yml` | 不覆盖多 worker / PG live |
| `production_secret_gate.py` | ✅ | 生产 env 仍须运维签字 |
| `run_plan_closure_gate.py` | ✅（`--allow-blocked`） | iOS 2 项 BLOCKED 可跳过 |
| `grafana_smoke_gate.py` | ✅ | P2-03 scrape 未 staging live |
| `bootstrap_gate_e2e.py` | ✅（需 live URL） | 依赖 `RELEASE_GATE_BASE_URL` 变量 |
| `postgres_compose_pytest_gate.py` | ✅ nightly（`SKIP_POSTGRES_COMPOSE=1` 默认） | Docker PG 未在 CI runner 证明 |
| iOS macOS pipeline | ❌ | P2-02 |
| Server release DevStack | ❌ | P2-01 |
| NOTIFY webhook live test | ❌ | P2-03 |

---

## 8. 文档与流程债务

| 项 | 状态 |
|----|------|
| `full_stack_expert_review.md` 变更记录停在 2026-07-24 | 未反映 P0–P2 实施结果 |
| `plans/README.md` 无统一 closure tracker | **本文补位** |
| P1-01 Plan 重复 DoD 段矛盾 | 需删第二段 §7 或同步 `[x]` |
| P0-01 DoD issue closure | 无 issue 链接 |
| `production_backup_restore.md` 验证清单全 `[ ]` | 备份恢复未签字 |
| REF § 服务端发版「当前未实现」 | 与 P2-01「Done MVP」表述冲突 — **以本文 §3 P2-01 为准** |

---

## 9. 建议 closure 顺序（可执行）

```
Phase A — 能上线不失控（1–2 周）
  1. GAP-P0-01-SEC-02 + GAP-P0-01-CI-01：清 settings.json 弱口令 + CI 接 secret gate
  2. GAP-P0-02-PRE-02：写 deployment_topology.md（单 worker 直到 PG 完成）
  3. GAP-P0-02-DOD-01：backup runbook 补 DB SSOT
  4. GAP-P2-03-OPS-01 + E2E-01/02：staging 配 webhook + 故意 fail 验通知/回滚
  5. GAP-P1-02-E2E-02 + GAP-P1-04-E2E-01：DevStack 30min smoke 签字

Phase B — 架构阻断（2–4 周）
  6. GAP-P0-02-S6-01/02：Postgres migrate + compose pytest
  7. GAP-P0-02-S2-01 + S3-01：多 worker + stress
  8. GAP-P0-02-S5-01：wechat_minigame E2E

Phase C — 三平面完整（4–8 周）
  9. GAP-P2-01-E2E-01：Server release DevStack
  10. GAP-P2-02-E2E-01：iOS TestFlight E2E
  11. W-P1-2 / W-P2-1 / W-P2-2：巨石拆分（新 Plan，勿再堆）
  12. C-P1-3：WebGL/小游戏 spec + Plan
```

---

## 10. 验证命令速查

```powershell
# Secret gate（本地）
py -3 portals/common/core/scripts/production_secret_gate.py

# 生产 fail-fast（需 production env）
cd portals/common/core
$env:APP_ENV="production"
py -3 -c "from config import require_production_secrets; require_production_secrets()"

# Registry 并发
py -3 -m pytest portals/common/core/tests/test_project_repo_concurrency.py -q

# P2-03 单测（mock，不等于 E2E）
py -3 -m pytest portals/common/core/tests/test_observability_incident_loop.py -q

# Ops runtime
py -3 -m pytest portals/common/core/tests/test_ops_runtime_service.py -q

# Dev 快速发版（需 DevStack）
powershell -File scripts/Invoke-DevQuickPublish.ps1

# Grafana metrics 形状（需 Portal 运行）
py -3 portals/common/core/scripts/grafana_smoke_gate.py
```

---

## 11. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-29 | Closure implementation pass：evidence + gates + master gate PASS（iOS BLOCKED） |

**维护规则**：任何 Plan Step 勾 `[x]` 或评审项标关闭，必须在本表对应行追加 **Evidence** 列链接（CI run / runbook 签字 / E2E 日志），否则视为 **假绿**。
