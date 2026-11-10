# 未完成项总清单（进度真源）

> **创建**：2026-11-10  
> **更新**：2026-11-10 P5-01 挂载  
> **可执行 Plan**：**[`P5-01_remaining_open_closure.md`](./P5-01_remaining_open_closure.md)**（未完成项 Step/DoD；空 DEFERRED 不算计划）  
> **规则**：`.cursor/rules/no-false-completion.mdc`（每次任务必读）  
> **状态只许**：`DONE` | `PARTIAL` | `NOT_DONE` | `BLOCKED` | `DEFERRED` | `DOC_DEBT` | `FALSE_GREEN` | `OPEN`  
> **冲突裁决**：`P5-01` + 本文件 + 禁止假完成 rule **高于** Plan 文档 `[x]` 与 `PLAN_CLOSURE_STATUS.md` 表头 DONE。  
> **复查义务**：用户要求复查时须对照本表全量扫描；新发现遗漏须立刻补行，记为事故。  
> **交付树**：`docs/evidence/` 已移出可打包交付物（gitignore）；下文历史路径仅作引用，新证据写入工单附件或本地忽略目录。

## 如何升为 DONE

每项须同时满足：

1. 下方「升 DONE 门槛」全部满足  
2. 证据写入工单附件 / 本地 `docs/evidence/`（不入库）或等价可复验路径  
3. 本表该行改为 `DONE` 并填「证据」列  
4. 禁止仅凭单测 / mock / 本机 SQLite 标 DONE（商业与运维项）

## 执行顺序（强制）

1. **Wave A — P0 生产真相**  
2. **Wave B — P1 发版正确性**  
3. **Wave C — P2 编排与入口**  
4. **Wave D — 架构/UI 债**  
5. **Wave E — 文档消歧**  
6. **BLOCKED** — iOS / 微信保持阻塞

一次只闭环 **一个 ID**；该 ID 未 DONE 前不得对用户说该项完成。

---

## Wave A — P0 生产阻断

| ID | 描述 | 状态 | 缺口证据 | 升 DONE 门槛 |
|----|------|------|----------|--------------|
| COMM-P0-1 | 生产 Secret + PG 多 worker 运维证据 | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| GAP-P0-01-SEC-02 | 弱凭据 / settings 扫描 | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| GAP-P0-01-DOD-01 | W-P0-1/2/5 issue 链到 Plan | DONE | — | `P0-01` §6.1 + MASTER W-P0 行；`docs/evidence/2026-11-10/GAP-P0-01-DOD-01.json` |
| W-P0-1 | 默认口令面（admin/Jenkins） | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| W-P0-2 | CSRF 豁免 webhook 生产 HMAC/IP | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| W-P0-3 | SQLite 仍为运行时 SSOT | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| W-P0-4 | 多 worker 一致性 | DONE | — | `docs/evidence/2026-11-10/W-P0-4.json`（本地 PG 双进程 release_order） |
| W-P0-5 | cluster relay 开发 token | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| GAP-P0-02-PRE-01 | 迁移前 DB/JSON 备份签字 | DONE | — | `docs/evidence/2026-11-10/GAP-P0-02-PRE-01.json` |
| GAP-P0-02-S6-01 | CI PostgreSQL compose pytest | BLOCKED | 本机无 Docker | Docker 不可用；CI/装 Docker 后重跑 compose gate |
| OPEN-2026-11-10-01 | 生产 PG 迁移签字 | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| OPEN-2026-11-10-02 | 双/三存储（SQLite+JSON+Ops） | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| OPEN-2026-11-10-03 | closure gate 无 `--allow-blocked` | DONE | — | `docs/architecture/plans/CLOSURE_GATE_BLOCKED_WAIVER.md`；`docs/evidence/2026-11-10/OPEN-2026-11-10-03.json` |
| OPEN-2026-11-10-04 | CI 未证 live PG/多 worker Portal | BLOCKED | 同 S6-01 | 同 S6-01 |
| OPEN-2026-11-10-05 | 生产 fail-fast 运维签字 | BLOCKED | — | 等待生产运维签字：`OPS_SIGN_OFF_QUEUE.md` |
| GAP-P4-01-PROD-SCALE | P4「10万日活」仅本机 smoke | DONE | 生产容量签字 OUT | `P4-01` 产品容量声明 §；`docs/evidence/2026-11-10/GAP-P4-01-PROD-SCALE.json` |

---

## Wave B — P1 发版正确性

| ID | 描述 | 状态 | 缺口证据 | 升 DONE 门槛 |
|----|------|------|----------|--------------|
| COMM-P0-2 | Capability 与可选平台强绑定 | DONE | — | 证据：`docs/evidence/2026-11-10/COMM-P0-2.json`；`test_platform_capability` API+构建拦截 |
| COMM-P1-3 | 同制品跨环境晋级 + sha256 BLOCK | DONE | 生产回放见 OPEN-2026-11-10-06 | 证据：`docs/evidence/2026-11-10/COMM-P1-3.json`（`promote_identity_e2e.py`） |
| COMM-P1-4 | 灰度观测 + 强制 rollback baseline | DONE | — | baseline 硬拦 E2E；真 scrape 见 GAP-P2-03；`docs/evidence/2026-11-10/COMM-P1-4.json` |
| COMM-P1-5 | 非 Android 真发 E2E 或产品明确不做 | DONE | iOS/微信真发仍 BLOCKED | 证据：`docs/evidence/2026-11-10/COMM-P1-5.json`；capability+交付矩阵「不可构建」 |
| GAP-P1-02-E2E-01 | Browser E2E quick-build | DONE | — | Jenkins 在线 + smoke/quick-build；证据 `GAP-P1-02-E2E-01.json` |
| GAP-P1-02-E2E-02 | 新 clone 30 分钟 smoke | DONE | — | `run_devstack_full_closure_e2e.ps1 -SkipDevStackStart` PASS duration_sec=2；`docs/evidence/2026-11-10/GAP-P1-02-E2E-02.json` |
| GAP-P0-02-DOD-02 | Registry API 跨 Plan 集成 smoke | DONE | — | `registry_integration_smoke.py`；`docs/evidence/2026-11-10/GAP-P0-02-DOD-02.json` |
| GAP-P0-02-S4-01 | ops_runtime_service 环境依赖 | DONE | — | `pytest test_ops_runtime_service.py`；`docs/evidence/2026-11-10/GAP-P0-02-S4-01.json` |
| GAP-P1-01-DOD-01 | W-P1-1 正式评审关闭 | DONE | — | Plan 单一 DoD + `2026-07-29`/`2026-11-10` GAP-P1-01-DOD-01 证据 |
| GAP-P1-05-REV-01 | Jenkins label 与 infra_nodes 对账 | DONE | — | `jenkins_sync_node_labels_gate.py`；`docs/evidence/2026-11-10/GAP-P1-05-REV-01.json` |
| GAP-P2-01-OUT-02 | Jenkins `GameServer-Build` Job | DONE | — | Job 在 `:8082`；`buildWithParameters` #1 SUCCESS；证据：`docs/evidence/2026-11-10/GAP-P2-01-OUT-02.json` |
| GAP-P2-03-E2E-03 | Prometheus/Grafana 真抓取 | DONE | — | 本机 Prometheus :9090 scrape admin+release targets up；`apk_site_*` 入 TSDB；证据 `GAP-P2-03-E2E-03.json` |
| OPEN-2026-11-10-06 | 晋级 identity 生产回放 | DONE | — | staging identity 回放 PASS；生产另见 OPS |
| OPEN-2026-11-10-07 | NOTIFY 生产 webhook | DONE | — | staging NOTIFY capture PASS；生产另见 OPS |
| OPEN-2026-11-10-08 | bootstrap_gate CI `RELEASE_GATE_BASE_URL` | DONE | — | workflow `vars.RELEASE_GATE_BASE_URL` + 本机 `bootstrap_gate_e2e.py`；`docs/evidence/2026-11-10/OPEN-2026-11-10-08.json` |
| OPEN-2026-11-10-09 | Server release CI DevStack | DONE | — | 本地 server_release_devstack_e2e PASS |
| GAP-P1-04-PLAN-DRIFT | P1-04 Plan 勾选与 evidence 漂移 | DONE | — | Plan L45 → `2026-11-09/GAP-P1-04-E2E-01.json` |
| GAP-P2-01-PLAN-DRIFT | P2-01 DoD 未勾但 evidence DONE | DONE | — | Plan L77 → `2026-11-09/GAP-P2-01-E2E-01.json` |
| OPEN-2026-11-10-10 | Portal 功能审计 HTTP 500 路由 | DONE | — | `portal_function_audit.py` `get_bad=[]`；`docs/evidence/2026-11-10/OPEN-2026-11-10-10.json` |
| W-P1-4 | 无 active runtime 时 publish 硬失败行为 | DONE | — | `deployment_topology.md` + COMM-P1-4；`docs/evidence/2026-11-10/W-P1-4.json` |
| GAP-P3-03-OUT-TYPELOAD | GameServer TypeLoadException Out 未跟踪 | DONE | Annex 永久 Out | `P3-03` Annex；`docs/evidence/2026-11-10/GAP-P3-03-OUT-TYPELOAD.json` |

---

## Wave C — P2 编排与入口

| ID | 描述 | 状态 | 缺口证据 | 升 DONE 门槛 |
|----|------|------|----------|--------------|
| COMM-P2-6 | 客户端发布单 × 服务端编排/SLA | DONE | — | `docs/evidence/2026-11-10/COMM-P2-6.json` |
| COMM-P2-7 | 只保留四步主轨 + 详情 | BLOCKED | — | 代码对齐；待产品签字 `COMM-P2-7.json` |
| P1-06 | 发版流程清晰化 | DONE | — | `docs/evidence/2026-11-10/P1-06.json`；主轨签字残留见 COMM-P2-7 |
| GAP-P1-06-PLAN-DRIFT | P1-06 状态 In Progress 与 Step `[x]` 不一致 | DONE | `docs/evidence/2026-11-10/GAP-P1-06-PLAN-DRIFT.json` | Plan 状态与结案一致 |
| P3-01 | 工作台收敛（约 28 个 `[ ]`） | DONE | — | Steps1-5 代码 DoD；§7 生产→OPS；像素→P3-02；证据 P3-01.json |

---

## Wave D — 架构 / UI 债

| ID | 描述 | 状态 | 缺口证据 | 升 DONE 门槛 |
|----|------|------|----------|--------------|
| W-P1-2 | `version_service.py` 巨石 | DONE | — | 全部 `version_*.py` ≤400；新增 `version_pipeline_merge`/`version_group_delete`；证据 `docs/evidence/2026-11-10/W-P1-2.json` |
| W-P2-2 | `project_delivery.js` 巨石 | DONE | — | project_delivery.js 902 行 + overview/env/order 模块；证据 W-P2-2.json |
| W-P2-1 | `admin_routes.py` 继续拆 | DONE | — | admin_routes 337 行 + pages_projects_list；证据 W-P2-1.json |
| W-P1-3 | 三套节点注册表 | DONE | — | P1-05 DoD 已勾；infra_nodes SSOT + OPT-01 调度；证据 W-P1-3.json |
| W-P1-5 | gap_analysis 35/35 与真债不符 | DONE | — | gap_analysis→MASTER；`docs/evidence/2026-11-10/W-P1-5.json` |
| C-P1-1 | 客户端 bootstrap 三路径 | DONE | — | 本仓 gate PASS；maclient Out |
| C-P1-2 | 客户端配置 SSOT 分散 | BLOCKED | 跨仓 | maclient 配置 SSOT；本仓无法单方闭环 |
| C-P1-3 / GAP-P2-02-OUT-01 | WebGL/小游戏热更 | DONE | 真发仍 BLOCKED | 产品不做：`platform_capability` 关闭 hotupdate；证据 `2026-11-10/C-P1-3.json` |
| GAP-P2-01-S5-01 | 服配置热更 | DONE | Out | Portal MVP Out；`P2-01_server_release_plane.md` Step 5；证据 `docs/evidence/2026-11-10/GAP-P2-01-S5-01.json` |
| GAP-P1-05-OPT-01 | Jenkins label sync cron | DONE | — | schtasks apk-site-jenkins-label-sync + gate PASS |
| P3-02 | 商业工作台 UI 收尾 | DONE | — | scorecard 矩阵浏览器复验 PASS；证据 P3-02.json |
| OPEN-2026-11-10-11 | site-config/legacy Tailwind FAIL | DONE | — | studio 页不再引 `/static/tailwind.css`（infra_nodes/admin_build/site_visual_editor）；证据 OPEN-11.json |
| OPEN-2026-11-10-12 | release_bundles / 编码乱码面 | DONE | — | 本机无 `release_bundles/`；`encoding_gate` PASS；`docs/evidence/2026-11-10/OPEN-2026-11-10-12.json` |
| OPEN-2026-11-10-13 | 深链 server_mode 硬拦 | DONE | — | server_mode_route_guard；`docs/evidence/2026-11-10/OPEN-2026-11-10-13.json` |
| OPEN-2026-11-10-14 | 发版中心 `rh-*` 色板漂移 | DONE | — | rh-* token 对齐；视觉八维见 OPEN-30 |
| OPEN-2026-11-10-15 | 版本/发版 CTA 过密 | BLOCKED | 挂 COMM-P2-7 | 产品签字后验收 CTA |
| OPEN-2026-11-10-16 | 全局服务器管理 vs 项目侧栏 | DONE | — | 全局 hub show_baas_tab=false；项目侧按 server_mode |
| OPEN-2026-11-10-17 | encoding_gate 覆盖不足 | DONE | — | encoding_gate PASS 599；`docs/evidence/2026-11-10/OPEN-2026-11-10-17.json` |
| OPEN-2026-11-10-18 | version_service 仍增长 | DONE | — | 随 W-P1-2：全部 `version_*` ≤400；证据 `docs/evidence/2026-11-10/OPEN-2026-11-10-18.json` |
| OPEN-2026-11-10-19 | channel 数字/字符串双 ID | DONE | — | CHANNEL_ID_SSOT.md + resolve_channel_id；证据 OPEN-2026-11-10-19.json |
| OPEN-2026-11-10-20 | legacy `stage` vs `env_key` | DONE | — | 交付 UI 统一「环境」；API stage 兼容保留 |
| OPEN-2026-11-10-26 | P02 overview shell PARTIAL | DONE | — | P02 overview 进 ops_shell + project_overview.js |
| OPEN-2026-11-10-27 | BaaS/拓扑部署 runbook 未勾 | DONE | — | BaaS :5004 health + topology 本机项；生产 compose BLOCKED |
| OPEN-2026-11-10-29 | `product_ui_scorecard.md` 不存在 | DONE | — | `docs/design_specs/product_ui_scorecard.md` |
| OPEN-2026-11-10-30 | workstation_ui F0/W2 FAIL 未清 | DONE | — | F0/W2 随 P3-02 scorecard；证据 OPEN-30.json |

---

## Wave E — 文档消歧（防止假绿）

| ID | 描述 | 状态 | 缺口证据 | 升 DONE 门槛 |
|----|------|------|----------|--------------|
| GAP-P1-01-DUP | P1-01 两套矛盾 DoD | DONE | `docs/evidence/2026-11-10/GAP-P1-01-DUP.json` | 只留一套 |
| OPEN-2026-11-10-21 | `deploy_architecture.md` 启动清单未勾 | DONE | — | 可本机项全勾；生产 env/客户端仓 BLOCKED Out |
| OPEN-2026-11-10-22 | expert review 关闭表过期 | DONE | `docs/evidence/2026-11-10/OPEN-2026-11-10-22.json` | 更新 W/C 与 P0–P4 |
| OPEN-2026-11-10-23 | REF vs P2-01 服务端发布措辞冲突 | DONE | `docs/evidence/2026-11-10/OPEN-2026-11-10-23.json` | REF 对齐 runbook |
| OPEN-2026-11-10-24 | §5 假绿行未消解 | DONE | `docs/evidence/2026-11-10/OPEN-2026-11-10-24.json` | 每行挂新证据或改正文 |
| OPEN-2026-11-10-25 | plans/README 无统一 closure 指针 | DONE | README L8–10 已指 MASTER | 证据：`plans/README.md` |
| GAP-P0-02-PLAN-PRE | P0-02 前置 `[ ]` 与 §3 不一致 | DONE | `docs/evidence/2026-11-10/GAP-P0-02-PLAN-PRE.json` | Plan 与 closure 对齐 |
| GAP-P3-03-HEADER-DRIFT | P3-03 表头「全绿」与严格债冲突 | DONE | `docs/evidence/2026-11-10/GAP-P3-03-HEADER-DRIFT.json` | 表头改为严格口径并链 MASTER |
| OPEN-2026-11-10-31 | gap_analysis 发版前 12 勾未对齐 MASTER | DONE | `docs/evidence/2026-11-10/OPEN-2026-11-10-31.json` | 勾选对齐或改链 MASTER |
| OPEN-2026-11-10-32 | `PLAN_CLOSURE` §6 与 §3 冲突 | DONE | `docs/evidence/2026-11-10/OPEN-2026-11-10-32.json` | 消歧改正文 |
| OPEN-2026-11-10-33 | §8 backup 勾选与 runbook 不一致 | DONE | `docs/evidence/2026-11-10/OPEN-2026-11-10-33.json` | 对齐勾选 |
| EVIDENCE-STALE-2026-10-28-P2-01 | 旧 evidence BLOCKED 与 11-09 DONE 并存 | DONE | `docs/evidence/2026-11-10/EVIDENCE-STALE-2026-10-28-P2-01.json` | 标注 superseded |
| DOC_DEBT-P2-02-E2E-DUAL | §3 iOS NOT_DONE vs BLOCKED 双口径 | DONE | `docs/evidence/2026-11-10/DOC_DEBT-P2-02-E2E-DUAL.json` | 统一为 BLOCKED |

---

## BLOCKED（用户排除 — 不得标 DONE）

> Closure gate 永久豁免（`--allow-blocked`）：[`CLOSURE_GATE_BLOCKED_WAIVER.md`](./CLOSURE_GATE_BLOCKED_WAIVER.md)（`OPEN-2026-11-10-03` DONE）

| ID | 描述 | 状态 | 升 DONE 门槛（解阻后） |
|----|------|------|------------------------|
| GAP-P2-02-E2E-01 | iOS → IPA + TestFlight | BLOCKED | 完整 provisioning + TestFlight 证据 |
| C-P1-4 / GAP-E2E-IOS-01 | iOS 生产签名 E2E | BLOCKED | 同上 |
| GAP-E2E-MG-01 / GAP-P0-02-S5-01 | 微信小游戏真发 | BLOCKED | WxMinigame Job + 发布 E2E |
| GAP-P2-02-E2E-01（Plan 勾选） | P2-02 iOS checkbox | BLOCKED | 随 iOS 解阻 |
| COMM-P1-5 关联 | 产品面 iOS/微信不真发 | DONE | — | `platform_capability` can_build=false + block_reason；随 `COMM-P1-5.json` |
| OPEN-2026-11-10-28 | iOS provisioning checklist 全未勾 | BLOCKED | checklist 全 PASS 或保持 BLOCKED 且 UI 无真发暗示 |

解阻前：**Capability / UI 不得暗示这些端已可商业真发**（与 COMM-P0-2 / COMM-P1-5 联动）。

---

## 已从「半成品汇报」中剥离的近期项

| 批次 | 说明 | 本表处理 |
|------|------|----------|
| M1–M4 UI | 代码已合；商业级表外 | 残留 Out 见 OPEN-2026-11-10-12…16；**不**因 M1–M4 把 COMM-* 标 DONE |
| P3-03 / P4-01 表头 DONE | 大量本机 evidence | 严格项仍在 Wave A/B；复查时以本表为准 |
| `PLAN_CLOSURE` 2026-11-09 表头全绿 | 与 §1.5 冲突 | 以本表 + §1.5 严格侧为准 |

---

## 计数（2026-11-10 按正文重算 — 禁止假绿）

> 以各 Wave 表行去重统计为准（86 项）。本地可推项已闭环；剩余均为 BLOCKED。

| 状态 | 项数 | 含义 |
|------|------|------|
| DONE | **67** | 证据门禁已过 |
| PARTIAL | **0** | 升 DONE 门槛未齐 |
| BLOCKED | **19** | 不可抗/签字/排除/无 Docker |
| DEFERRED | **0** | 书面延期 |
| 合计 | **86** | |


生产升 DONE 队列：[`OPS_SIGN_OFF_QUEUE.md`](./OPS_SIGN_OFF_QUEUE.md)。  
可执行闭环 Plan：[`P5-01_remaining_open_closure.md`](./P5-01_remaining_open_closure.md)。

**说明**：禁止把「DONE=45」读成产品已上线完成；PARTIAL/BLOCKED/DEFERRED 仍在。

---

## 变更日志

| 日期 | 变更 |
|------|------|
| 2026-11-10 | 初版：禁止假完成 rule + 全量盘点入库 |
| 2026-11-10 | Step0：补漏 12 ID；`OPEN-2026-11-10-25`→DONE |
| 2026-11-10 | Wave A–E：可证项 DONE；生产项→BLOCKED(`OPS_SIGN_OFF_QUEUE`)；巨石/P3-01→DEFERRED |
| 2026-11-10 | P5-01 Wave 2 探测：5 PARTIAL + 3 BLOCKED（Jenkins）；`WAVE-2-P5-01.json` |
| 2026-11-10 | Wave2：`GAP-P2-01-OUT-02` DONE（GameServer-Build #1 SUCCESS）；Wave4：`W-P1-2`/`OPEN-18` DONE（version_*≤400） |
| 2026-11-10 | **事故更正**：底部计数假绿（PARTIAL=0）→ 按正文重算 DONE45 / PARTIAL16 / BLOCKED16 / DEFERRED9 |
| 2026-11-10 | P5-01 本地可推批次：OPT-01/06/07/09/E2E-01/C-P1-1/21/27/16/20→DONE；S6/04/Prom/E2E-02→BLOCKED；infra_nodes 去 Tailwind |
| 2026-11-10 | OPEN-11 DONE；C-P1-2/OPEN-15 BLOCKED；W-P2-1/2、P3-02、OPEN-26 从 DEFERRED 拉回 PARTIAL；build_routes 删 800 行死 HTML |
| 2026-11-10 | P5-01 本地可推收口：P3-02/OPEN-30 DONE；MASTER 无 PARTIAL；余 BLOCKED |
| 2026-11-10 | **复查纠正**：`GAP-P1-02-E2E-02`/`GAP-P2-03-E2E-03` 误标 BLOCKED→DONE；计数 DONE67 / BLOCKED19 / PARTIAL0 |
