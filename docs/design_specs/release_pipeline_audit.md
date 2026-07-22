# 发版管理全流程审计

> 审计日期：2026-07-20  
> 目标：区分合理/不合理/伪实现/缺口；提供 dev/prod 双路径操作手册。  
> 关联计划：发版管理全流程梳理与改造（不改 plan 文件，本文为实现交付物）。

## 1. 合理设计（保留并强化）

| 模块 | 说明 | 实现 |
|------|------|------|
| Scope env×channel×platform | 与 bootstrap 参数一致 | `scope_resolver.py`, `delivery_scope.py` |
| ReleaseOrder 审计容器 | 构建可重复，发版可追溯 | `release_order_service.py` |
| Jenkins 参数来自版本组 pipeline | 业务只改 VC/配置 | `request_build`, `jenkins.py` |
| Precheck OSS/字段/runtime | 发布前阻断 | `bundle_service.run_scope_precheck` |
| Publish → Bundle 快照 | 客户端读 published bundle | `publish_release_order`, `/api/public/runtime-bootstrap` |
| Channel Journey 双管线 | 构建 6 步 / 发版 7 步 | `resolve_channel_*_journey` |
| Server-driven delivery-actions | 按钮由后端决定 | `resolve_delivery_actions` |

## 2. 不合理 / 需收敛

| 问题 | 改造 |
|------|------|
| 双真相源 bootstrap vs version-resolve | bootstrap 为权威；version-resolve 响应加 `prefer_runtime_bootstrap` 提示 |
| Scope publish-bundle 绕过审批 | 生产环境禁用直发（需 release order） |
| Gray/rollout 假字段 | UI 移除灰度按钮；后端保留 metadata 但不宣称可用 |
| Lazy 构建同步 | `sync_building_release_orders` + Journey API 主动 sync |
| Jenkins 失败卡 building | 新增 `build_failed` 状态 |
| 多入口 commercial-release | 文档标记 legacy；主路径为 Journey |

## 3. 伪实现 / 空壳（改造后）

| 项 | 状态 |
|----|------|
| `prechecking`/`publishing`/`verifying` 中间态 | **已写入 DB** |
| Verify 手动 ok/false | **已改**：ok=true 时跑 bootstrap HEAD smoke |
| Build Journey 固定 62% 进度 | **已改**：按 Jenkins 状态 + webhook/SSE |
| Release Journey 无发布单 | **已改**：ensure-release-order + 创建按钮 |
| 测试设备页 | **已实现** CRUD + stage 绑定 |
| CI 仅 fixture | bootstrap_gate_e2e 全链 + nightly 硬失败 |

## 4. 缺口清单（剩余）

**无剩余 P1+ 缺口**（2026-07-22 全栈修复完成）。运维面持续改进见 `docs/runbooks/`。

---

## 5. Dev 操作手册（5 步）

**前提**：Manifest 已 bootstrap-scopes；版本组 pipeline 已配置；拓扑已绑定且 runtime 运行中。

| 步 | 操作 | URL / API |
|----|------|-----------|
| 1 | 打开环境详情，选 scope | `/admin/projects/{id}/environments/{env}` |
| 2 | 客户端页签 → **构建** | `.../channels/{ch}/build?platform=android` |
| 3 | 选 VC → **触发构建** | `POST .../versions/{vid}/quick-build` |
| 4 | 构建完成后 → **发版**入口 | `.../channels/{ch}/release?platform=&version_id=` |
| 5 | **创建发布单**（若无）→ **预检** → **发布** → **验证** | `ensure-release-order`, `precheck`, `publish`, `verify` |

**一键（Dev）**：`POST /api/projects/{id}/delivery-attempts/quick-publish`  
body: `{ "env_key", "channel_id", "platform", "version_id", "skip_build": false }`  
要求：`artifacts_ready` 或自动触发 build 后返回 `{ phase: "building" }`。

---

## 6. Prod 操作手册

| 步 | 与 Dev 差异 |
|----|-------------|
| 1–3 | 同 Dev |
| 4 | 发布单 **完整计划**（form_depth=full） |
| 5 | 预检 → **待审批** → 审批 → 发布 → smoke 验证 |
| 禁止 | Scope 直发 `publish-bundle`（API 返回 403） |

**一键（Prod）**：`quick-publish` 在 `awaiting_approval` 停止；已 `approved` 时可继续 publish。

---

## 7. 按钮 → API → DB 映射（主路径）

| UI 按钮 | API | DB 副作用 |
|---------|-----|-----------|
| 触发构建 / quick-build | `POST .../quick-build` | release_orders.status=building, payload.build_job_id |
| 构建完成（sync） | lazy + journey poll | status=artifacts_ready 或 build_failed |
| 创建发布单 | `POST .../ensure-release-order` | INSERT release_orders draft/artifacts_ready |
| 执行预检 | `POST .../release-orders/{id}/precheck` | INSERT prechecks; status=ready/awaiting_approval/precheck_failed |
| 审批 | `POST .../approve` | release_approvals; status=approved |
| 发布 | `POST .../publish` | INSERT release_bundles; scopes.active_bundle_id |
| 验证 | `POST .../verify` | bootstrap smoke; status=verified/verify_failed |
| 客户端拉包 | `GET /api/public/runtime-bootstrap` | 只读 bundle.client |

---

## 8. 改造文件索引

| 文件 | 改动 |
|------|------|
| `release_order_service.py` | build_failed, sync_all, quick_publish, verify smoke, journey BFF |
| `project_delivery.py` | ensure-release-order, quick-publish routes |
| `project_channel_release_journey.js` | 创建发布单、移除假灰度 |
| `project_channel_build_journey.js` | 真实 progress_pct |
| `test_build_status_transitions.py` | 构建状态单测 |
| `test_release_publish_integration.py` | 预检/发布集成 |
| `scripts/nightly_release_chain_smoke.py` | CI/nightly 门禁 |
