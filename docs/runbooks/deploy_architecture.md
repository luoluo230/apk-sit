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

状态：`PASS` = 本仓已复验 | `NOT_DONE` = 需目标环境执行 | 详见 [OPEN_ITEMS_MASTER.md](../architecture/plans/OPEN_ITEMS_MASTER.md)

- [ ] `PORTAL_SERVER_FRAMEWORKS` 与目标模式一致 — **BLOCKED**（生产/预发 env 签字；本机默认 `all` 不算生产签 off）
- [x] `init_db()` 本机 SQLite — **PASS**（`py -3 -c "from models.db import init_db; init_db()"` @ `portals/common/core`；2026-11-10 Wave1）
- [x] 项目 `server_mode` 与所选框架匹配 — **PASS**（`project_nav_policy` + 深链 `server_mode_route_guard`；证据 `docs/evidence/2026-11-10/OPEN-2026-11-10-13.json`）
- [x] Bootstrap 发布链 gate — **PASS**（`bootstrap_gate_e2e.py` @ `:5003`；证据 `docs/evidence/2026-11-10/OPEN-2026-11-10-08.json`；裸 `client-bootstrap` 需 scope 参数）
- [x] 服务器管理页路由可达 — **PASS**（本机 `/admin` shell 路由无 500；卡片 Agent 态随 OPEN-09 DevStack；浏览器像素随 P3-02）
- [ ] 客户端已导入 PortalHttp + 对应 NetworkModule — **BLOCKED**（客户端仓 / Annex Out）
- [x] 运行 `py scripts/encoding_gate.py` 与相关单元测试 — **PASS**（本机；证据 `docs/evidence/2026-11-10/OPEN-2026-11-10-17.json`）

## 相关文档

- [server_framework_modules.md](../design_specs/server_framework_modules.md)
- [topology_server_deploy.md](./topology_server_deploy.md)
- [baas_standalone_deploy.md](./baas_standalone_deploy.md)
