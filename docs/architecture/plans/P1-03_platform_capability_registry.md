# P1-03：Platform Capability Registry

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 1–2 周 |
| 依赖 | 无（与 build_grid 代码共存） |
| 评审项 | W-P2-3, 18 平台 vs 3 构建 Job |
| 状态 | **Done**（2026-07-28） |

---

## 1. 目标

UI 与 API **只承诺 build_grid 能构建的平台**；其余平台标为「目录项 / 客户端占位 / 即将支持」。

---

## 2. Capability 模型

`services/build/platform_capability.py` — 合并 `PLATFORM_TO_JOB` + `PLATFORM_CATALOG` + 显式 profile。

---

## 3. 分步实施

### Step 1：Capability API（2 天） ✅

- `GET /api/admin/platforms/capabilities`
- `GET /api/admin/projects/{id}/platforms/enabled`
- `tests/test_platform_capability.py`

**验收**

- [x] android/ios/wechat_minigame `can_build=true`
- [x] switch `can_build=false`, `catalog_only=true`

---

### Step 2：项目设置 UI badge（2 天） ✅

- `project_delivery.js` 平台 Tab badge（overview 平台白名单）
- `project_overview.css` cap-badge 样式

**验收**

- [x] Switch 显示「目录项 / 暂不支持构建」

---

### Step 3：Version / Journey 门禁（2 天） ✅

- `request_build` → `assert_build_ready`（含 capability 校验）
- `resolve_delivery_actions` 不可构建平台禁用 quick_build
- `resolve_channel_build_journey` 隐藏不可构建 Tab

**验收**

- [x] switch quick-build 路径 400（capability gate）
- [x] android 不受影响

---

### Step 4：DB migration 对齐（1 天） ✅

- `scope_resolver.resolve_scope` auto_create 调用 `assert_scope_creation_allowed`
- `ALLOW_CATALOG_ONLY_SCOPE=1` 开发覆盖

**验收**

- [x] wechat_minigame scope 可创建
- [x] switch scope 默认拒绝

---

## 4. 完成定义（DoD）

- [x] Capability API + UI badge + build 门禁三处一致
- [x] `docs/design_specs/platform_capability_registry.md`
- [x] W-P2-3 关闭（运营不可误选 Switch 触发构建）
