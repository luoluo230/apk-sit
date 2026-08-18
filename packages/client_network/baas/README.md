# BaaS 客户端网络模块（Casual BaaS Client Network）

与 **轻度 BaaS 服务器框架**（`casual_baas_server`）配对使用。

## 部署 / 导入

| 侧 | 动作 |
|----|------|
| Portal | 部署时启用 `PORTAL_SERVER_FRAMEWORKS=baas`（或 `all`） |
| Unity | 复制 `Runtime/` 与 `../common/Runtime/PortalHttp.cs` 到 maclient |

## Bootstrap

```
GET /api/public/client-bootstrap
  或
GET /api/public/baas-bootstrap
```

查询参数：`game_id`, `game_key`, `env`（或 `env_key`），可选 `service_id`

## 鉴权头

| Header | 说明 |
|--------|------|
| `X-Baas-Api-Key` | 服务 API Secret |
| `X-Baas-Service-Id` | 可选，须与 URL 中 service_id 一致 |
| `Authorization: Bearer {token}` | 玩家会话（登录后） |
| `X-Baas-Player-Id` | 玩家 ID |

## REST 基址

Bootstrap 返回 `public_api_base`，例如 `/api/baas/v1/{service_id}`。

## Portal 扩展编辑器（BaaS 专用）

- 休闲服务控制台 `/admin/projects/{id}/casual-services/{service_id}`
- 项目设置 → 服务器架构

## 开发同步脚本

```powershell
.\scripts\Sync-DevStackClientConfig.ps1 -Mode baas
```

## 示例代码

见 `Runtime/BaasNetworkModule.cs`
