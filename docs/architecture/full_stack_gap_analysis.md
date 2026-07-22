# 全链路架构梳理与缺口清单

> 审计日期：2026-07-22  
> 分支：`newVersion`（含 P0/P1 发版重构，commit `67a8c0a`）  
> 目的：从 **Web 管理端 → Jenkins 构建 → 发布/Bundle → 游戏客户端 → 游戏服务器** 梳理完整闭环，结合日常迭代与商业发布场景，列出真实缺口、BUG 与伪实现，供后续排期使用。  
> 关联真源：`docs/full_release_chain_architecture.md`（2026-06-11，部分接口描述已落后于代码）

---

## 0. 结论摘要（能否支撑「快速迭代游戏」）

| 维度 | 现状 | 能否闭环 |
|------|------|----------|
| Dev 日常：改代码 → 构建 → 装包 → 热更 | 主路径已统一到 Channel Build/Release Journey + ReleaseOrder | **基本可用**，但依赖 Ops Runtime 已启动、管线/Jenkins 配置齐全 |
| Dev 一键发版 | `quick-publish` API 存在 | **可用**（development），失败点多在 runtime/OSS |
| Prod 商业发布 | 预检 → 待审批 → 发布 → 验证 | **流程完整**，审批仍为本库 SQLite，无外部工单 |
| 客户端拉包 | `GET /api/public/runtime-bootstrap` 读 published bundle | **权威路径正确**；旧客户端若仍调 `version-resolve` 可能漂移 |
| 服务端拓扑/联网 | 发布时冻结 topology + network_profile | **逻辑完整**；Ops 启停、cluster 同步仍偏手工 |
| CI/门禁 | 单元测试 90/92；e2e gate 部分 `continue-on-error` | **不能作为唯一质量闸** |

**总体判断**：Web 侧发版状态机与 Bundle 快照模型已成型，**闭环骨架在**，但 **构建反馈、验证深度、Ops 前置条件、文档/接口漂移、若干 UI/聚合 BUG** 仍会打断「无人值守快速迭代」。下面按链路展开。

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

**仍存在的双真相风险**：`GET /api/runtime/version-resolve` 读 VersionRow；新客户端必须用 `runtime-bootstrap`。

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
| 3 | 构建完成（poll sync） | `sync_building_release_orders` | 无 webhook，页面需刷新或等 journey poll |
| 4 | Channel Release Journey → 创建/选发布单 → 预检 | OSS 产物 HEAD 可达 | OSS 403/路径错 → precheck_failed |
| 5 | 发布 → 验证 | verify smoke | smoke 仅查 URL 非空，**不 HEAD** |
| 6 | 客户端装 APK，冷启动 | `runtime-bootstrap` | game_id/game_key 与 manifest 不一致 → 401 |

**Dev 捷径**：`POST .../quick-publish`（development）可串联 build→precheck→publish→verify，但仍受 runtime/OSS 约束。

### 2.2 商业发布（Production）

| 步 | 与 Dev 差异 |
|----|-------------|
| 发布单表单 | `form_depth=full`，需填写验证/回滚计划等 |
| 预检通过后 | 状态 `awaiting_approval`，需人工审批 API |
| Scope 直发 | `POST .../scopes/{id}/publish-bundle` **默认禁止** production |
| 一键发版 | `quick-publish` 在 `awaiting_approval` 停止，不会越权发布 |

**缺口**：审批仅 SQLite `release_approvals`，无钉钉/飞书/企业微信、无双人复核、无审批 SLA。

### 2.3 热修复 / 回滚

| 操作 | API | 说明 |
|------|-----|------|
| 发布单回滚 | `POST .../release-orders/{id}/rollback` | 恢复历史 bundle 为 active |
| Scope 回滚 | `POST .../scopes/{id}/rollback` | 需非 production 或显式策略 |
| Jenkins 重构建 | Journey 内 rebuild / quick-build | 不自动作废旧 bundle |

**缺口**：无自动「灰度 5% → 全量」；`rollout_percentage` 等字段存在但**无分桶逻辑**。

### 2.4 多平台 / 多渠道

- Scope 已按 **env × channel × platform** 四维拆分（DB migration 已做）。
- 同一 VersionName 下多 VersionCode 靠 scope + platform 隔离。
- **BUG 风险**：`GET /api/release/scopes/{id}` 查 active bundle 时未传 platform（见 §4.2）。

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

### 4.1 文档 / 接口漂移（P0 文档债）

| 项 | 文档声称 | 代码现状 | 影响 |
|----|----------|----------|------|
| `GET /api/public/release-config` | `full_release_chain_architecture.md` §6.2 | **无路由**；仅 `release_context.py` 注释 | 新接入方按文档集成会 404 |
| `POST /api/gm-ops/release/*` | 同上 + 旧 GM 页 | **已归档**，仅 `archives/runtime/gm_page_dump.html` | 运维习惯旧 GM 会找不到入口 |
| `scope_id` 格式 | 真源文档写 3 段 | 实现为 **4 段含 platform** | CI fixture、外部脚本可能查错 scope |
| `active_bundle_id` 真源 | 文档写 VersionRow + Bundle | **以 SQLite bundle + scope 为准** | 版本列表展示的 publish 状态可能滞后 |

**建议**：更新 `full_release_chain_architecture.md` §6，或在本文件标记 supersede；对外只宣传 `runtime-bootstrap`。

### 4.2 Web / BFF 层

| ID | 类型 | 描述 | 位置 / 证据 |
|----|------|------|-------------|
| W-01 | BUG | **Overview 渠道过滤计数错误**：`channel_id=wechat` 时 production 环境 `delivery_line_count` 期望 1 实际 2 | `test_delivery_scope.py::test_project_overview_channel_filter_counts` FAIL；`channel_journey_bff.project_overview` |
| W-02 | BUG | **Versions 页带 env_key 仍 302**：仅 `?env_key=development` 无 channel 会 redirect 到 environment 页 | `admin_routes.project_versions_page` L478–480；`test_versions_with_env_key_renders` FAIL |
| W-03 | 缺口 | `project_delivery.js` 仍 ~2426 行，order-detail 未独立拆文件 | size gate 上限 2450，余量极小 |
| W-04 | 缺口 | 测试设备页 `/test-devices` 为 placeholder | `project_delivery.py` |
| W-05 | 缺口 | 任务/文档页 placeholder | 同上 |
| W-06 | 体验 | 发布单中间态 `prechecking/publishing/verifying` **从未写入 DB**，UI 只能显示静态「进行中」 | `order_constants` / audit doc §3 |
| W-07 | 体验 | P11/P12 发布单详情/表单距设计稿像素级仍有差距 | `release_order_detail_p19.md` checklist 未全 PASS |
| W-08 | 架构 | `project_delivery.py` 仍 ~966 行，API 路由未拆到 `routes/delivery/*` 子模块 | P1 仅拆 helpers |

### 4.3 构建 / Jenkins 层

| ID | 类型 | 描述 | 位置 / 证据 |
|----|------|------|-------------|
| B-01 | 缺口 | **无 Jenkins webhook**，构建完成靠 poll | `order_build_sync.sync_release_order_build_status`；audit P1 |
| B-02 | BUG | Jenkins SUCCESS 后 `finalize_apk_from_jenkins_build` 异常被 **静默 swallow** | `order_build_sync.py` ~276–277 → artifacts 可能仍 missing |
| B-03 | 缺口 | Jenkins 流水线稳定性、OSS 上传失败重试属于运维面，Web 仅标记 build_failed | 需 runbook |
| B-04 | 缺口 | 旧 `/admin/build/trigger` 与非 commercial 路径仍并存 | `build_routes.py` |
| B-05 | 风险 | 本地 `data/jenkins_instances/*` 与仓库 Jenkins job 配置易污染 git | 当前未 commit（正确） |

### 4.4 发布 / Bundle 层

| ID | 类型 | 描述 | 位置 / 证据 |
|----|------|------|-------------|
| P-01 | 缺口 | **Verify smoke 弱于 precheck**：只检查 bootstrap 字段非空，不做 HTTP HEAD | `order_publish_flow.run_bootstrap_smoke_for_order` L288–296 |
| P-02 | 缺口 | precheck **强制 runtime 已运行**，Dev 未启 Ops 时无法完成发版 | `order_publish_flow` L76–78；日常迭代门槛高 |
| P-03 | BUG | `GET /api/release/scopes/{id}` 取 active bundle **未传 platform** | `routes/release/scopes.py` |
| P-04 | 缺口 | 灰度字段（rollout_percentage、gray_*）无服务端分桶 | bootstrap snapshot 有字段，客户端未实现 |
| P-05 | 缺口 | Scope 级 `publish-bundle` 与 ReleaseOrder 双路径，易误用 | production 已禁，dev 仍可用 |
| P-06 | 架构 | `find_release_order_for_version` 在 crud 与 build_sync **重复实现** | 维护成本 |

### 4.5 Ops / 游戏服务器层

| ID | 类型 | 描述 | 位置 / 证据 |
|----|------|------|-------------|
| O-01 | 缺口 | Runtime 启停、cluster sync 分散在 Ops 大模块 `helpers.py`（7000+ 行） | 难测试、难扩展 |
| O-02 | 缺口 | 发布前要求 topology 与 runtime 对齐，但 **无自动「发布成功后通知 server reload catalog」** | 客户端热更靠 OSS；服务端逻辑/config 靠重启？需 maclient/server 文档对齐 |
| O-03 | 缺口 | Agent 心跳、远程启停节点 — API 存在但与 Release Journey **无一键联动** | 需从 Journey「环境问题」链到 Ops |
| O-04 | 风险 | `datetime.utcnow()` 弃用警告 | `ops/helpers.py` test warning |

### 4.6 客户端层（maclient，仓库外）

| ID | 类型 | 描述 | 说明 |
|----|------|------|------|
| C-01 | 缺口 | 仓库内 **无 Unity 客户端源码**，仅文档 `gameframework_loader_decision.md` | PlayMode 测试在外部 repo |
| C-02 | 风险 | 旧客户端仍调 `version-resolve` | 与 published bundle 漂移；API 已标 deprecated |
| C-03 | 缺口 | bootstrap 字段与 `commercial_startup_sequence_gate.py` 对齐，但 **Editor 本地覆盖 network 的行为**需 maclient 保证 | 真源文档 §5.4 |
| C-04 | 缺口 | HybridCLR + Addressables 失败降级策略（离线包/重试）未在 Web 侧可视化 | 排障靠客户端日志 |

### 4.7 CI / 测试 / 门禁

| ID | 类型 | 描述 | 位置 / 证据 |
|----|------|------|-------------|
| T-01 | BUG | 全量 pytest **92 中 2 FAIL**（delivery_scope） | 见 W-01、W-02 |
| T-02 | 缺口 | `bootstrap_gate_e2e` / `nightly_release_chain_smoke` **continue-on-error: true** | `.github/workflows/release-platform-gate.yml` |
| T-03 | 缺口 | CI scope fixture 仍用 **3 段 scope_id**（无 platform） | gate 脚本 vs DB migration |
| T-04 | 缺口 | 无自动化「装 APK → 调 bootstrap → 拉 catalog」端到端（需设备/模拟器） | 仅脚本探针 |

---

## 5. 场景 × 缺口矩阵

| 场景 | 阻塞级缺口 | 烦人但可绕过 |
|------|------------|--------------|
| 新人第一天配项目 | Manifest、渠道、环境 scope、版本组 pipeline | W-02 versions 跳转；文档 drift |
| 日常 Dev 构建 | Jenkins 实例、pipeline 四步 | B-01 poll 慢；B-02 finalize 静默失败 |
| Dev 发版给测试 | **P-02 runtime 必须运行** | P-01 verify 太弱 |
| Prod 上线 | 审批无外部系统 | P-04 无灰度 |
| 客户端联调 | game_id/key、bootstrap | C-02 旧 API |
| 线上事故回滚 | rollback API 可用 | 无自动告警；Ops 手工 |
| 多平台 iOS+Android | scope 四维 | P-03 scope API platform |

---

## 6. 推荐修复优先级

### P0 — 不打断主路径（1–2 周）

1. 修复 **W-01 / W-02** 测试失败（overview 渠道计数、versions env gate）
2. 修复 **B-02** finalize 异常：至少写 event + build_failed 或重试队列
3. 对齐 **文档**：更新 `full_release_chain_architecture.md` 接口列表，标注 GM/release-config 已移除
4. 修复 **P-03** scope API platform 参数

### P1 — 提升「快速迭代」体验（2–4 周）

1. **Jenkins webhook** 或 SSE 推送构建状态（替代纯 poll）
2. **Verify 增强**：复用 `_check_remote_artifact` 对 bootstrap URL HEAD
3. **Dev 预检 runtime 策略**：development 环境可选「warn 不 block」或提供 mock runtime
4. 拆完 `project_delivery.py` API 子路由；`delivery_order_detail.js` 独立
5. CI：bootstrap gate 改为 fail PR；scope fixture 改为 4 段

### P2 — 商业发布完备（1–2 月）

1. 灰度：实现 rollout 分桶或删除 UI/DB 假字段
2. 外部审批集成（Webhook 出 + 回调 approve）
3. P11/P12 设计稿 1:1 验收
4. Ops 与 Journey 联动：预检失败「一键启动 runtime」

### P3 — 长期

1. maclient 与 apk-site 联合 e2e（PlayMode + bootstrap gate）
2. 拆分 `ops/helpers.py`
3. 测试设备页真实接入 version-resolve 选版

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

## 9. 测试现状（2026-07-22）

```
portals/common/core: pytest tests/ → 90 passed, 2 failed
  FAIL test_delivery_scope.DeliveryScopeTests.test_project_overview_channel_filter_counts
  FAIL test_delivery_scope.VersionsEnvGateTests.test_versions_with_env_key_renders

release 专项 35 passed（build/journey/publish/integration）
size gate: OK（facade + 子模块 + commercial_release ≤150 行）
```

---

## 10. 变更记录

| 日期 | 说明 |
|------|------|
| 2026-07-22 | 初版：P1 提交后全链路梳理；基于代码走读 + pytest + 既有 audit 文档 |

**维护建议**：每完成一个 P0/P1 修复，在本文件对应条目打 `[FIXED yyyy-mm-dd]`，并同步更新 `release_pipeline_audit.md` §4 剩余缺口。
