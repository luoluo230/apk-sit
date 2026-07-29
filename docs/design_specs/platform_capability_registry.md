# Platform Capability Registry

Plan: P1-03 — UI/API 只承诺 build_grid 能构建的平台。

## 数据源优先级

1. `services/build/build_grid.py` — `PLATFORM_TO_JOB` 决定 `can_build`
2. `data/platforms.py` — `PLATFORM_CATALOG` 展示名与 Unity BuildTarget
3. `services/build/platform_capability.py` — 显式覆盖（webgl、wechat_minigame 等）

## API

| 端点 | 说明 |
|------|------|
| `GET /api/admin/platforms/capabilities` | 全目录 + capability flags |
| `GET /api/admin/projects/{id}/platforms/enabled` | 项目白名单 ∩ capability |

## Badge 语义

| badge | 含义 | 示例平台 |
|-------|------|----------|
| `buildable` 🟢 | 可 Jenkins 构建 | android, ios, wechat_minigame |
| `client_only` 🟡 | 客户端/占位 | webgl |
| `catalog_only` ⚪ | 目录项，不可构建 | switch, ps5 |

## 门禁

- `request_build` / `assert_build_ready` — 不可构建平台返回 400
- `resolve_channel_build_journey` — 构建 Journey 仅展示可构建平台 Tab
- `resolve_scope` auto_create — 默认拒绝 catalog_only（`ALLOW_CATALOG_ONLY_SCOPE=1` 开发覆盖）

## 测试

```bash
cd portals/common/core
py -m pytest tests/test_platform_capability.py -q
node --check static/project_delivery.js
```
