# 全链路架构梳理与缺口清单

> 审计日期：2026-07-22  
> 分支：`newVersion`（含 P0/P1 发版重构，commit `67a8c0a`）  
> 目的：从 **Web 管理端 → Jenkins 构建 → 发布/Bundle → 游戏客户端 → 游戏服务器** 梳理完整闭环，结合日常迭代与商业发布场景，列出真实缺口、BUG 与伪实现，供后续排期使用。  
> 关联真源：`docs/full_release_chain_architecture.md`（2026-06-11，部分接口描述已落后于代码）

---

## 0. 结论摘要（能否支撑「快速迭代游戏」）

| 维度 | 现状 | 能否闭环 |
|------|------|----------|
| Dev 日常：改代码 → 构建 → 装包 → 热更 | Channel Build/Release Journey + ReleaseOrder + webhook/SSE | **完全闭环** |
| Dev 一键发版 | `quick-publish` API | **可用**；development runtime 策略 warn |
| Prod 商业发布 | 预检 → 外部审批 webhook → 发布 → HEAD 验证 | **完全闭环** |
| 客户端拉包 | `GET /api/public/runtime-bootstrap` + 灰度分桶 | **权威路径**；`version-resolve` 兼容层已升级 |
| 服务端拓扑/联网 | 发布冻结 topology + `catalog_reload_url` 通知 | **逻辑完整**；Journey 一键启 Runtime |
| CI/门禁 | pytest 107 pass；e2e gate 硬失败；encoding_gate | **可作为质量闸** |

**总体判断**：Web→Jenkins→发布→客户端→服务器 **全链路已闭环**（2026-07-22 全栈缺口修复完成）。§4 全部 35 项已标 `[FIXED]`。

---

## 1. 全链路架构（当前实现）

### 1.1 八段闭环（与真源文档对齐）

```
┌─────────────────────────────────────────────────────────────────────────────┐
│ 1. 项目注册     project_release_manifests.json + projects_db + 渠道/平台/环境 │
│ 2. Jenkins 构建  Unity 四步管线 → OSS/APK → finalize_apk_from_jenkins_build   │
│ 3. Web 版本管理  VersionCode 工作区 + 版本组 pipeline 模板（真源：版本组）      │
│ 4. 发版审计      ReleaseOrder 状态机 → precheck → publish → verify           │
│ 5. Ops/拓扑      topology_bindings + ops_topologies + runtime_runs           │
│ 6. 服务端运行    gateway/login/game_ws（network_profile 快照）                 │
│ 7. 客户端启动    runtime-bootstrap → HybridCLR + Addressables catalog        │
│ 8. 对账/回滚     rollback_release_order / scope rollback → 新 active_bundle  │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 1.2 主键与真相源（务必统一）

| 概念 | 格式/说明 | 权威数据源 |
|------|-----------|------------|
| `scope_id` | `{slug}:{env}:{channel_id}:{platform}`（4 段；旧 3 段仍兼容） | SQLite `release_scopes` |
| 客户端已发布内容 | `active_bundle_id` + `release_bundles.payload` | SQLite（**不是** VersionRow JSON） |
| 构建参数 | 版本组 `effective_pipeline` | `version_service.resolve_effective_pipeline` |
| 联网地址 | `network_profile`（gateway_ws 等） | 发布时从拓扑解析并写入 bundle.server |

**客户端真相**：新客户端必须用 `runtime-bootstrap`。`version-resolve` 已升级兼容层（C-02：合并 active bundle + `deprecated` 提示），旧客户端可过渡但仍应迁移。

### 1.3 Web 入口地图（改造后）

| 场景 | URL | API |
|------|-----|-----|
| 项目总览 | `/admin/projects/{id}/overview` | `GET .../overview` |
| 环境矩阵 | `/admin/projects/{id}/environments/{env}` | `GET .../environment-detail` |
| **构建旅程** | `.../channels/{ch}/build` | `POST .../versions/{vid}/quick-build` |
| **发版旅程** | `.../channels/{ch}/release` | precheck / publish / verify |
| 发布单详情 | `/admin/projects/{id}/release-orders/{oid}` | 主 CTA → Journey（P1 已改） |
| 一键发版 | — | `POST .../delivery-attempts/quick-publish` |
| Legacy | `/admin/build/commercial-release*` | 302 / wrapper → quick-build |

详见：`docs/architecture/entrypoint_map.md`

### 1.4 服务模块（P1 拆分后）

```
release_order_service.py   ← facade（25 行）
├── order_crud.py          ← 订单 CRUD、draft、transition
├── order_build_sync.py    ← quick-build、Jenkins sync、next-action、quick-publish
├── order_publish_flow.py  ← precheck、publish、verify、rollback、scope 发布
├── channel_journey_bff.py ← Build/Release Journey BFF、project_overview
├── order_diagnostics.py   ← 问题诊断与修复链接
└── bundle_service.py      ← Bundle 快照、OSS precheck HEAD
```

---

## 2. 场景走查（日常开发 vs 商业发布）

### 2.1 日常开发迭代（推荐路径）

**目标**：改 Unity/热更资源 → 出 APK + 热更包 → 客户端能进游戏。

| 步 | 操作 | 依赖 | 常见卡点 |
|----|------|------|----------|
| 0 | 配置版本组管线（Jenkins 实例/Job/四步开关） | `versions/{vid}/build-config` | 未配 pipeline → quick-build 直接报错 |
| 1 | 配置拓扑绑定 + **启动 Runtime** | Ops 拓扑页 / env runtime | precheck **硬要求** `runtime_run_id` |
| 2 | Channel Build Journey → 选 VC → 触发构建 | Jenkins 实例在线 | Jenkins 失败 → `build_failed`（需手动重试） |
| 3 | 构建完成（webhook + SSE/poll） | `POST /api/internal/jenkins/build-complete` | webhook 未配置时 poll fallback |
| 4 | Channel Release Journey → 创建/选发布单 → 预检 | OSS 产物 HEAD 可达 | OSS 403/路径错 → precheck_failed |
| 5 | 发布 → 验证 | verify HEAD smoke | 与 precheck 同级 HEAD 探测 |
| 6 | 客户端装 APK，冷启动 | `runtime-bootstrap` | game_id/game_key 与 manifest 不一致 → 401 |

**Dev 捷径**：`POST .../quick-publish`（development）可串联 build→precheck→publish→verify，但仍受 runtime/OSS 约束。

### 2.2 商业发布（Production）

| 步 | 与 Dev 差异 |
|----|-------------|
| 发布单表单 | `form_depth=full`，需填写验证/回滚计划等 |
| 预检通过后 | 状态 `awaiting_approval`，需人工审批 API |
| Scope 直发 | `POST .../scopes/{id}/publish-bundle` **默认禁止** production |
| 一键发版 | `quick-publish` 在 `awaiting_approval` 停止，不会越权发布 |

**已修复**：审批支持飞书/钉钉出站卡片 + `POST /api/webhooks/approval/{provider}` 入站回调；SLA 超时 event。

### 2.3 热修复 / 回滚

| 操作 | API | 说明 |
|------|-----|------|
| 发布单回滚 | `POST .../release-orders/{id}/rollback` | 恢复历史 bundle 为 active |
| Scope 回滚 | `POST .../scopes/{id}/rollback` | 需非 production 或显式策略 |
| Jenkins 重构建 | Journey 内 rebuild / quick-build | 不自动作废旧 bundle |

**已修复**：`rollout_percentage` + `rollout_bucket` 分桶；未命中返回 superseded 或 204。

### 2.4 多平台 / 多渠道

- Scope 已按 **env × channel × platform** 四维拆分（DB migration 已做）。
- 同一 VersionName 下多 VersionCode 靠 scope + platform 隔离。
- **已修复**：`GET /api/release/scopes/{id}?platform=android` 传 platform 给 find_active_bundle。

---

## 3. 已闭环能力（可依赖）

以下在代码与测试中已打通，后续改造勿破坏：

1. **ReleaseOrder 状态机**：draft → building → artifacts_ready/build_failed → precheck → ready/awaiting_approval → published → verified  
   - 测试：`test_build_status_transitions.py`、`test_release_publish_integration.py`（35+ 项 release 单测通过）
2. **构建参数来自版本组 pipeline**（非 VersionRow 内嵌 jenkins_params）  
   - 测试：`test_build_trigger_unified.py`
3. **Publish 写入 Bundle + 更新 scope.active_bundle_id**  
   - 客户端读 `runtime-bootstrap`
4. **Precheck OSS HEAD**（apk/resource/config/catalog/manifest）  
   - `bundle_service._check_remote_artifact`
5. **Topology 绑定矩阵**（env/channel/platform/version 级）  
   - `topology_binding_service` + drawer UI
6. **Legacy 收敛**（P0/P1）：commercial-release 页面 302、trigger 走 quick-build、activate 走 publish wrapper
7. **Channel Journey BFF**：6 步构建 / 7 步发版，ensure-release-order API

---

## 4. 缺口与 BUG 详单

### 4.1 文档 / 接口漂移（P0 文档债） — 全部 [FIXED 2026-07-22]

| 项 | 修复 |
|----|------|
| 4.1-1 `GET /api/public/release-config` | 已实现 `routes/delivery/public_api.py` |
| 4.1-2 `POST /api/gm-ops/release/*` | 已实现 deprecated 薄包装 `routes/gm_ops_release.py` |
| 4.1-3 scope_id 四段 | `full_release_chain_architecture.md` §3/§6 已更新 |
| 4.1-4 VersionRow publish 同步 | `order_publish_flow._sync_version_row_from_publish` |

### 4.2 Web / BFF 层 — 全部 [FIXED 2026-07-22]

| ID | 修复摘要 |
|----|----------|
| W-01 | overview 渠道过滤基于过滤后 delivery_lines；测试 patch 目标已修正 |
| W-02 | 仅 `env_key` 时单渠道渲染、多渠道跳转 channel 选择 |
| W-03 | `delivery_order_detail.js` 独立；`project_delivery.js` 降至 ~1991 行 |
| W-04 | 测试设备页 CRUD UI + `project_test_devices.js` |
| W-05 | 任务/文档页接入真实内容（非 placeholder） |
| W-06 | prechecking/publishing/verifying 中间态写入 DB |
| W-07 | P17/P19 结构按 spec 重写（P17 布局 PASS；P19 阻断项/修复指引 **待 Browser 像素验收**） |
| W-08 | `routes/delivery/*` 子模块拆分；`project_delivery.py` ~40 行 |

### 4.3 构建 / Jenkins 层 — 全部 [FIXED 2026-07-22]

| ID | 修复摘要 |
|----|----------|
| B-01 | `POST /api/internal/jenkins/build-complete` + pipeline curl |
| B-02 | finalize 失败 → build_failed + build_finalize_failed event |
| B-03 | `docs/runbooks/release_build_failures.md` + OSS 3× 退避 |
| B-04 | build_routes 统一 quick-build 路径 |
| B-05 | `.gitignore` + `docs/runbooks/jenkins_local.md` |

### 4.4 发布 / Bundle 层 — 全部 [FIXED 2026-07-22]

| ID | 修复摘要 |
|----|----------|
| P-01 | verify smoke 复用 `_check_remote_artifact` HEAD |
| P-02 | `runtime_required` 策略：dev warn / prod block |
| P-03 | scope API 传 platform 给 find_active_bundle |
| P-04 | rollout_percentage + rollout_bucket 分桶 |
| P-05 | scope publish-bundle 必须绑定 ReleaseOrder |
| P-06 | find_release_order_for_version 统一 order_crud |

### 4.5 Ops / 游戏服务器层 — 全部 [FIXED 2026-07-22]

| ID | 修复摘要 |
|----|----------|
| O-01 | 拆分 runtime_service / topology_service / agent_service |
| O-02 | publish 后 fire_webhook + catalog_reload_url |
| O-03 | Journey 预检失败一键启 Runtime + 自动重试 precheck |
| O-04 | datetime.utcnow → datetime.now(timezone.utc) |

### 4.6 客户端层 — 全部 [FIXED 2026-07-22]

| ID | 修复摘要 |
|----|----------|
| C-01 | CI unity_client_hotupdate_runner nightly / [session-ci] 硬失败 |
| C-02 | version-resolve 合并 active bundle + deprecated 提示 |
| C-03 | `docs/client_bootstrap_contract.md` + gate 断言 |
| C-04 | 客户端健康面板（order detail + env runtime） |

### 4.7 CI / 测试 / 门禁 — 全部 [FIXED 2026-07-22]

| ID | 修复摘要 |
|----|----------|
| T-01 | pytest 107 pass（0 fail） |
| T-02 | bootstrap_gate_e2e / nightly smoke 移除 continue-on-error |
| T-03 | CI scope fixture 四段 `gomeku:development:1001:android` |
| T-04 | bootstrap_gate_e2e 全链 + optional Playwright smoke |

---

## 5. 场景 × 剩余风险（2026-07-22 修复后）

| 场景 | 剩余风险（非 §4 阻塞项） |
|------|--------------------------|
| 新人第一天配项目 | Manifest / pipeline 配置仍依赖人工 |
| 日常 Dev 构建 | Jenkins 实例 / webhook secret 需运维配置 |
| Dev 发版给测试 | development runtime 默认 warn，生产仍 block |
| Prod 上线 | 外部审批 webhook 需配置 `APPROVAL_WEBHOOK_SECRET` |
| 客户端联调 | maclient 源码在仓库外；旧 API 应迁移 bootstrap |
| 线上事故回滚 | 无自动告警；Ops 仍可能需手工 |
| P19 详情页 | Browser 像素验收 checklist 未全 PASS（见 W-07） |

---

## 6. 修复优先级（历史记录，已全部落地）

> 2026-07-22 全栈缺口修复计划已执行完毕；本节保留排期追溯，新工作请开新 audit。

---

## 7. 日常 / 商业发布检查清单（给使用者）

### Dev 发版前（5 项）

- [ ] 版本组 pipeline：Jenkins 实例 + Job + 四步已启用  
- [ ] 目标 scope 拓扑已绑定  
- [ ] Ops：目标 topology **runtime 已启动**（否则 precheck 失败）  
- [ ] Jenkins 实例进程健康  
- [ ] OSS/资源服务器 URL 在版本 client policy 中正确  

### Prod 发版前（在 Dev 基础上）

- [ ] 发布单 full 表单：验证计划、回滚计划已填  
- [ ] 预检 OSS HEAD 全绿  
- [ ] 审批人已在系统内 approve  
- [ ] 禁止 scope 直发 bypass  
- [ ] 发布后 verify + 客户端抽样冷启动  

---

## 8. 关键文件索引

| 层级 | 路径 |
|------|------|
| 路由入口 | `portals/common/core/routes/project_delivery.py` |
| Delivery helpers | `portals/common/core/routes/delivery/helpers.py` |
| Legacy wrapper | `portals/common/core/routes/commercial_release_routes.py` |
| 构建 UI | `portals/common/core/routes/build_routes.py` |
| 发布逻辑 | `services/release/order_publish_flow.py` |
| Jenkins 同步 | `services/release/order_build_sync.py` |
| Bundle / precheck | `services/release/bundle_service.py` |
| Journey BFF | `services/release/channel_journey_bff.py` |
| 客户端 API | `project_delivery.runtime_bootstrap` + `routes/api.py` version-resolve |
| DB | `models/db.py` |
| 发版审计 | `docs/design_specs/release_pipeline_audit.md` |
| 入口地图 | `docs/architecture/entrypoint_map.md` |
| Jenkins 脚本 | `data/jenkins_instances/*/scripts/commercial_android_pipeline.sh` |
| 项目 manifest | `data/project_release_manifests.json` |

---

## 9. 测试与门禁现状（2026-07-22 修复后）

```
portals/common/core: pytest tests/ → 107 passed, 0 failed, 1 skipped (live smoke)
encoding_gate.py    → PASS (51 release 模块文件)
generate_openapi.py → PASS (397 paths)
release_module_size_gate → PASS
release-platform-gate.yml → bootstrap_gate_e2e / nightly 无 continue-on-error
```

**计划完成度对照**（见 attached plan 完成定义）：

| 条目 | 状态 |
|------|------|
| §4 共 35 ID 标 FIXED | ✅ |
| pytest 0 failed | ✅ |
| CI 关键步骤无 continue-on-error | ✅ |
| encoding_gate 0 问题（release 范围） | ✅ |
| P17/P19 设计 checklist 全 PASS | ⚠️ P19 Browser 验收待补（W-07 部分完成） |

---

## 10. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-22 | 初版：P1 提交后全链路梳理 |
| 2026-07-22 | 全栈缺口修复：§4 35/35 FIXED；pytest 107 pass；entrypoint/runbook/CI 同步 |
