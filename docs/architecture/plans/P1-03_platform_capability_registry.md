# P1-03：Platform Capability Registry

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 1–2 周 |
| 依赖 | 无（与 build_grid 代码共存） |
| 评审项 | W-P2-3, 18 平台 vs 3 构建 Job |

---

## 1. 目标

UI 与 API **只承诺 build_grid 能构建的平台**；其余平台标为「目录项 / 客户端占位 / 即将支持」，避免运营选 Switch 却无法构建。

---

## 2. Capability 模型

新建 `services/build/platform_capability.py`：

```python
CAPABILITY_BUILD = "build"           # Jenkins Job 存在
CAPABILITY_HOTUPDATE = "hotupdate"   # HybridCLR / 等效热更
CAPABILITY_STORE = "store"           # TestFlight / 微信后台上传
CAPABILITY_SCOPE = "scope"           # 可创建 release scope

PLATFORM_CAPABILITIES = {
  "android": {build, hotupdate, store: apk, scope},
  "ios": {build, hotupdate, store: testflight, scope},
  "wechat_minigame": {build, hotupdate: false, store: wx_backend, scope},
  "webgl": {build: false, hotupdate: false, scope: optional},
  # switch, ps5, ... → catalog_only
}
```

**数据源优先级**：

1. `build_grid.PLATFORM_TO_JOB` — build=true/false
2. `platforms.PLATFORM_CATALOG` — 展示名、unity_build_target
3. 未来：DB 表 `platform_capabilities`（本 Plan 先用代码常量）

---

## 3. 分步实施

### Step 1：Capability API（2 天）

**动作**

1. `GET /api/admin/platforms/capabilities` — 全 catalog + flags
2. `GET /api/admin/projects/{id}/platforms/enabled` — 过滤 project 白名单 + capability
3. 单元测试：`tests/test_platform_capability.py`

**验收**

- [ ] android/ios/wechat_minigame `can_build=true`
- [ ] switch `can_build=false`, `catalog_only=true`

---

### Step 2：项目设置 UI badge（2 天）

**动作**

1. `project_settings.js` / 平台 Tab：每平台显示
   - 🟢 可构建 / 🟡 仅客户端 / ⚪ 目录
2. 禁用「创建 VC」按钮当 `can_build=false` 且用户选构建 Journey（仍允许 Scope 占位若产品需要）

**改文件**

- `static/project_settings.js`
- `templates/project_settings.html`
- `translations/zh_CN/messages.json`

**验收**

- [ ] Browser：Switch 显示「暂不支持构建」

---

### Step 3：Version / Journey 门禁（2 天）

**动作**

1. `quick_build_version` / `request_build` 入口调用 `assert_build_ready(platform)`（已有 build_node path 可复用）
2. 错误信息明确：「平台 {x} 未接入构建网格，见 P1-05 或选 android」
3. `channel_journey_bff` 构建步隐藏不可构建平台 Tab

**改文件**

- `services/release/order_build_sync.py`
- `services/build/build_node_service.py`（如存在）
- `services/release/channel_journey_bff.py`

**验收**

- [ ] POST quick-build platform=switch → 400 + 可读 message
- [ ] android 仍正常

---

### Step 4：DB migration 对齐（1 天）

**动作**

1. 与 P0-02 Step 5 联动：`release_scopes.platform` CHECK 或应用层校验来自 capability
2. `scope_resolver` auto_create 时拒绝 catalog_only 平台（可 env 覆盖 `ALLOW_CATALOG_ONLY_SCOPE=1` dev）

**验收**

- [ ] wechat_minigame scope 可创建
- [ ] switch scope 默认拒绝

---

## 4. 完成定义（DoD）

- [ ] Capability API + UI badge + build 门禁三处一致
- [ ] 文档 `docs/design_specs/platform_capability_registry.md`（短 spec，可选）
- [ ] W-P2-3 关闭
