# 四模块部署架构总览

Web Portal、两套服务端框架、两套客户端网络模块的分层与上线步骤。

## 模块对照

| 模块 | 类型 | 环境变量 | Portal 入口 | 客户端包 |
|------|------|----------|-------------|----------|
| topology_server | 服务端 | `PORTAL_SERVER_FRAMEWORKS=topology` | 服务器管理 → 中重度 | `packages/client_network/topology` |
| casual_baas_server | 服务端 | `PORTAL_SERVER_FRAMEWORKS=baas` | 服务器管理 → 轻度 | `packages/client_network/baas` |
| topology_client | 客户端 | （随项目 server_mode） | — | 同上 topology |
| baas_client | 客户端 | （随项目 server_mode） | — | 同上 baas |

`PORTAL_SERVER_FRAMEWORKS=all`（默认）同时启用拓扑与 BaaS。

## 统一 Bootstrap（客户端唯一入口）

```
GET /api/public/client-bootstrap
GET /api/public/client-network-module
```

按项目 `server_mode` 自动分发：

- `topology` → runtime-bootstrap + WebSocket gateway
- `casual_baas` → baas-bootstrap + REST API 基址

兼容旧路径：`/api/public/runtime-bootstrap`、`/api/public/baas-bootstrap`

## 部署模式

### 模式 A：全量 Portal（推荐预发/生产）

```powershell
# 默认 PORTAL_SERVER_FRAMEWORKS=all
powershell -ExecutionPolicy Bypass -File scripts\Start-Portal5003.ps1
```

- 地址：`http://127.0.0.1:5003`
- 管理：服务器管理（中重度 + 轻度 Tab）

### 模式 B：仅拓扑中重度

```powershell
$env:PORTAL_SERVER_FRAMEWORKS = "topology"
# 启动 Portal 后仅注册 ops 路由，不加载 BaaS 公共 API
```

### 模式 C：仅轻度 BaaS（独立栈）

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1 -Background
```

- 地址：`http://127.0.0.1:5004`
- 入口：`/admin/baas`

## 客户端导入

1. 复制 `packages/client_network/common/Runtime/PortalHttp.cs`（HTTP 实现）
2. 复制对应模块 `topology/Runtime` 或 `baas/Runtime`
3. 同步配置：

```powershell
# 拓扑
.\scripts\Sync-DevStackClientConfig.ps1 -Mode topology

# BaaS
.\scripts\Sync-DevStackClientConfig.ps1 -Mode baas
```

## 架构部署包

Portal「服务器管理」页 → Tab 右侧 **下载架构部署包**：

| Tab | 文件 |
|-----|------|
| 中重度 | `topology-server-architecture.zip` |
| 轻度 | `baas-server-architecture.zip` |

解压合并到仓库根目录，按包内 `DEPLOY_README.md` 操作。

## 上线检查清单

- [ ] `PORTAL_SERVER_FRAMEWORKS` 与目标模式一致
- [ ] `init_db()` / 数据库迁移已执行
- [ ] 项目 `server_mode` 与所选框架匹配
- [ ] Bootstrap `/api/public/client-bootstrap` 返回 200
- [ ] 服务器管理页卡片状态正常
- [ ] 客户端已导入 PortalHttp + 对应 NetworkModule
- [ ] 运行 `py scripts/encoding_gate.py` 与相关单元测试

## 相关文档

- [server_framework_modules.md](../design_specs/server_framework_modules.md)
- [topology_server_deploy.md](./topology_server_deploy.md)
- [baas_standalone_deploy.md](./baas_standalone_deploy.md)
