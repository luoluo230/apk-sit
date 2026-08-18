# 拓扑客户端网络模块（Topology Client Network）

与 **拓扑服务器框架**（`topology_server`）配对使用。

## 部署 / 导入

| 侧 | 动作 |
|----|------|
| Portal | 部署时启用 `PORTAL_SERVER_FRAMEWORKS=topology`（或 `all`） |
| Unity | 复制 `Runtime/` 与 `../common/Runtime/PortalHttp.cs` 到 maclient |

## Bootstrap

```
GET /api/public/client-bootstrap
  或
GET /api/public/runtime-bootstrap
```

查询参数：`game_id`, `game_key`, `env_key`, `channel`, `platform`

## 网络注入

从响应 `network_profile` 注入：

- `gateway_ws`（必填）
- `login_http`, `game_ws`, `ops_http`（推荐）

maclient 资产：`ProtocolNetworkSettings.asset`

## Portal 扩展编辑器（拓扑专用）

- 拓扑工作台 `/admin/ops-platform/topology`
- 拓扑绑定抽屉（环境详情 / 发版矩阵）
- 版本构建配置 → 客户端策略（`client_policy`）
- 发版编辑 → 服务端 Tab

## 开发同步脚本

```powershell
.\scripts\Sync-DevStackClientConfig.ps1 -Mode topology
```

## 示例代码

见 `Runtime/TopologyNetworkModule.cs`
