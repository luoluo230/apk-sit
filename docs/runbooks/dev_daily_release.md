# Dev 日常发版 Runbook

面向 **development** 环境的推荐发版路径：自动启 Runtime、极简发布计划、一键 quick-publish。

---

## 前置条件

| 项 | 说明 |
|----|------|
| Jenkins | 目标 Job 在线，Agent 可用 |
| 项目 onboarding | 已完成渠道绑定与版本组配置（见 `docs/runbooks/project_onboarding.md`） |
| 拓扑 | development 环境已绑定拓扑，DevStack Agent 可达 |
| 产物 | 目标 VersionCode 构建完成或允许 quick-publish 触发构建 |

---

## 推荐路径（≤8 步）

### 1. 打开项目总览

`/admin/projects/{project_id}/overview`

确认 development 环境卡片 **Runtime** pill 为「运行中」；若为「已停止」，后续 precheck 会自动尝试启服。

### 2. 进入渠道发版 Journey

`/admin/projects/{project_id}/environments/development/channels/{channel_id}/release-journey?platform=android&version_id={version_id}`

### 3. 选择平台与 VersionCode

右上角切换平台，选择产物就绪的 VersionCode。

### 4. 创建 / 确认发布单

点击「创建发布单」或使用已有 draft 单；development 使用 **极简计划**（仅需 reason / owner）。

### 5. 执行预检（自动启 Runtime）

点击「执行预检」。development 环境默认带 `auto_ensure_runtime=1`：

- Runtime 已运行 → 直接预检
- Runtime 停止 → 自动启动并轮询（约 30s）后重试预检

预检失败且仅 Runtime 问题时，点击 **「自动启动 Runtime 并重试预检」**。

### 6. 发布

预检通过后点击「全量发布」。

### 7. 验证

发布完成后点击「验证通过」完成 smoke 验证。

### 8. （可选）客户端装包验证

从下载中心或 QR 安装 APK，确认热更与登录链路。

---

## API：一键 Dev 发版

```http
POST /api/projects/{project_id}/delivery-attempts/quick-publish
Content-Type: application/json

{
  "env_key": "development",
  "channel_id": "1001",
  "platform": "android",
  "version_id": "{version_uuid}",
  "skip_build": false,
  "force_build": false,
  "auto_verify": true
}
```

| 参数 | 类型 | 说明 |
|------|------|------|
| `env_key` | string | 固定 `development` |
| `channel_id` | string | 渠道 ID |
| `platform` | string | `android` / `ios` / `wechat_minigame` 等可构建平台 |
| `version_id` | string | 目标 VersionCode UUID |
| `skip_build` | bool | true 时跳过构建（产物须已就绪） |
| `force_build` | bool | true 时强制重新触发 Jenkins 构建 |
| `auto_verify` | bool | 发布后自动执行 verify（默认 true） |

**返回 `phase` 含义**

| phase | 说明 |
|-------|------|
| `building` | 已触发构建，需轮询发布单状态 |
| `awaiting_approval` | 仅 production；dev 不会出现 |
| `ready` / `published` / `verified` | 链路推进中或已完成 |

development 路径在 precheck 阶段会自动 `ensure_runtime`（与策略 `auto_ensure_runtime=true` 一致）。

---

## 预检 API（显式启 Runtime）

```http
POST /api/projects/{project_id}/release-orders/{order_id}/precheck?auto_ensure_runtime=1
```

production / staging 请勿带此参数；行为仍为 hard block。

---

## PowerShell 封装

```powershell
.\scripts\Invoke-DevQuickPublish.ps1 `
  -ProjectId GomeKu `
  -ChannelId 1001 `
  -Platform android `
  -VersionId "vc-uuid-here" `
  -BaseUrl "http://127.0.0.1:5000"
```

需已登录 Portal（session cookie）或使用内部测试账号。

---

## 故障排查

| 现象 | 处理 |
|------|------|
| 预检报 Runtime 超时 | 检查 Ops 拓扑 Agent 在线；手动打开运行工作台启动 |
| quick-publish 卡在 building | 查看 Jenkins 构建历史 |
| production 误触 auto ensure | production 策略 `runtime_required=block`，不会自动启服 |

---

## 相关 Plan

- `docs/architecture/plans/P1-04_dev_delivery_simplification.md`
- `docs/architecture/plans/P1-02` onboarding
- `docs/architecture/plans/P1-03` platform capability
