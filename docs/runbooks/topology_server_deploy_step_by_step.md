# 中重度拓扑服务器 — 逐步部署教程（完整版）

> 架构标识：`topology_server`  
> 配套客户端包：`dist/client-network-topology-*.zip`（或 `packages/client_network/topology`）  
> 默认 Bootstrap：`GET /api/public/client-bootstrap`（兼容 `/api/public/runtime-bootstrap`）

---

## 0. 你将得到什么

| 组件 | 说明 |
|------|------|
| Portal 管理端 | 项目、发版、拓扑绑定、Agent/Runtime 运维 |
| 拓扑服务端框架 | WebSocket Gateway、runtime-bootstrap 注入 |
| 部署压缩包 | `dist/topology-server-architecture.zip` |
| 客户端网络模块 | 独立 ZIP，按需导入 Unity，基础工程只保留 Gate 桩 |

**不包含**：Casual BaaS（`:5004`）、GameServer 二进制（需 maclient/game-server 另行部署）。

---

## 1. 环境准备（逐步检查）

### 1.1 操作系统

- Windows 10/11 或 Windows Server 2019+（本教程以 Windows PowerShell 为例）
- Linux/macOS 可用等价 shell，路径与 `powershell` 脚本需自行替换

### 1.2 必装软件

| 软件 | 版本建议 | 验证命令 |
|------|----------|----------|
| Git | 2.40+ | `git --version` |
| Python | 3.10–3.12 | `py -3 --version` |
| PowerShell | 5.1+ | `$PSVersionTable.PSVersion` |

### 1.3 拓扑全栈开发可选（Start-DevStack）

| 软件 | 用途 |
|------|------|
| .NET SDK 8+ | 编译/运行 GameServer |
| MongoDB | GameServer 持久化（DevStack 默认） |
| Redis | 会话/缓存（DevStack 默认） |
| Docker Desktop | 可选，替代本机 Mongo/Redis |

### 1.4 网络与端口

| 端口 | 服务 |
|------|------|
| 5003 | Portal 管理端（拓扑模式） |
| 15050 | GameServer Gateway WebSocket（DevStack 示例） |

确保防火墙放行本机回环 `127.0.0.1` 上述端口。

---

## 2. 获取代码与部署包

### 2.1 克隆 apk-site 主仓库

```powershell
cd E:\
git clone https://github.com/luoluo230/apk-sit.git apk-site
cd E:\apk-site
git checkout newVersion   # 或你的目标分支
```

### 2.2 解压拓扑架构部署包（覆盖合并）

若已从 `dist/` 或 Portal「服务器管理 → 中重度 → 下载架构部署包」取得 zip：

```powershell
# 假设 zip 在 E:\releases\
Expand-Archive -Path E:\releases\topology-server-architecture.zip -DestinationPath E:\apk-site -Force
```

**重要**：解压是**合并**到仓库根目录，不是新建子文件夹。合并后应存在：

- `scripts/Start-DevStack.ps1`
- `scripts/Start-Portal5003.ps1`
- `portals/common/core/server_frameworks/`
- `docs/runbooks/topology_server_deploy_step_by_step.md`（本文件）
- `manifest.json`（包内架构元数据）

### 2.3 阅读包内 manifest

```powershell
Get-Content E:\apk-site\manifest.json | ConvertFrom-Json
```

确认 `architecture` 为 `topology_server`，`env` 为 `PORTAL_SERVER_FRAMEWORKS=topology`。

---

## 3. Python 依赖安装

```powershell
cd E:\apk-site\portals\common\core

# 推荐：虚拟环境
py -3 -m venv venv
.\venv\Scripts\Activate.ps1

# 安装生产依赖
pip install -r requirements-prod.txt
# 开发/测试可选
pip install -r requirements-dev.txt
```

### 3.1 常见安装问题

| 现象 | 处理 |
|------|------|
| `pip` 找不到 | 使用 `py -3 -m pip install ...` |
| 编译 C 扩展失败 | 安装 Visual Studio Build Tools |
| `waitress` 缺失 | `pip install waitress` |

---

## 4. 配置环境变量

在 PowerShell 会话或系统环境变量中设置：

```powershell
$env:PORTAL_SERVER_FRAMEWORKS = "topology"
$env:APP_PORTAL_MODE = "admin"
# 可选：仅拓扑，不加载 BaaS 公共 API
$env:BAAS_STANDALONE = "0"
```

持久化（用户级）示例：

```powershell
[System.Environment]::SetEnvironmentVariable("PORTAL_SERVER_FRAMEWORKS", "topology", "User")
```

---

## 5. 初始化数据库

Portal 使用 SQLite（默认 `data/apk_site.db`）或 PostgreSQL（生产）。

```powershell
cd E:\apk-site\portals\common\core
py -3 -c "from models.db import init_db; init_db(); print('init_db OK')"
```

看到 `init_db OK` 表示表结构与迁移就绪。

---

## 6. 启动 Portal（仅拓扑）

### 6.1 方式 A — 仅 Portal :5003（推荐生产预发）

```powershell
cd E:\apk-site
powershell -ExecutionPolicy Bypass -File scripts\Start-Portal5003.ps1 -Background
```

等待输出包含 health 成功，或手动探测：

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:5003/health -UseBasicParsing
```

### 6.2 方式 B — 完整 DevStack（Portal + GameServer + 客户端同步）

需 maclient 与 game-server 路径可用：

```powershell
cd E:\apk-site
$env:MACLIENT_ROOT = "E:\maclient"
powershell -ExecutionPolicy Bypass -File scripts\Start-DevStack.ps1 -SkipSeed
```

参数说明：

| 参数 | 含义 |
|------|------|
| `-SkipGameServer` | 只起 Portal，不起 GameServer |
| `-SkipClientSync` | 不同步 Unity 客户端配置 |
| `-RestartPortal` | 强制重启 :5003 |

### 6.3 验证 Portal 框架门控

拓扑项目应能访问 runtime-bootstrap；BaaS-only 路由应返回 503：

```powershell
# 需有效 game_id / game_key（见下文创建项目）
$url = "http://127.0.0.1:5003/api/public/runtime-bootstrap?game_id=YOUR_GAME&game_key=YOUR_KEY&env_key=dev&channel=wechat&platform=android"
Invoke-WebRequest -Uri $url -UseBasicParsing
```

---

## 7. Portal 管理台 — 创建拓扑项目

1. 浏览器打开 `http://127.0.0.1:5003/login`
2. 使用管理员账号登录（首次部署见仓库 `data/users.json` 或 seed 脚本）
3. **项目列表 → 新建项目**
4. 关键字段：
   - **server_mode**：`topology`（或默认中重度）
   - **Game ID / Game Key**：写入客户端 HotUpdateConfig
5. **服务器管理 → 中重度服务器** Tab：
   - 查看拓扑卡片状态
   - 进入拓扑画布 / 绑定 / Agent 控制（按产品流程）

---

## 8. 同步客户端拓扑网络配置

客户端模块**未导入前**可先同步 Portal 地址到 maclient：

```powershell
cd E:\apk-site
powershell -ExecutionPolicy Bypass -File scripts\Sync-DevStackClientConfig.ps1 `
  -Mode topology `
  -MaclientRoot E:\maclient `
  -PortalBaseUrl http://127.0.0.1:5003
```

该脚本更新 `ProtocolNetworkSettings` 与 bootstrap 相关 StreamingAssets（若存在）。

---

## 9. 导入客户端拓扑网络模块（独立 ZIP）

基础 Unity 工程应只保留 `ClientNetworkModuleGate`（`MAClient.Network.Abstractions`）。

### 9.1 解压客户端包

```powershell
Expand-Archive -Path E:\apk-site\dist\client-network-topology-*.zip -DestinationPath E:\tmp\topology-module -Force
```

### 9.2 导入到 maclient

```powershell
cd E:\apk-site
powershell -ExecutionPolicy Bypass -File scripts\Import-ClientNetworkModule.ps1 `
  -Module topology `
  -MaclientRoot E:\maclient `
  -SourceDir E:\tmp\topology-module\ClientNetworkModule
```

导入后 Unity 应出现：

- `Assets/Modules/TopologyNetwork/`（轻量模块）
- 若 ZIP 含 `maclient/` 覆盖层：`HotUpdate/Framework/Network`、`Game/Network`、协议 Editor 等

### 9.3 Unity 编译验证

1. 打开 Unity Hub → 项目 `E:\maclient`
2. 等待脚本编译无 error
3. 确认程序集 `MAClient.Network.Topology` 已加载
4. `ClientNetworkModuleGate.HasTopologyModule == true`

---

## 10. Bootstrap 联调清单

| 步骤 | 命令/动作 | 期望 |
|------|-----------|------|
| 1 | `GET /health` | 200, ok=true |
| 2 | `GET /api/public/client-bootstrap?...` | 200, 含 network_profile |
| 3 | Unity 启动流程拉 bootstrap | gateway_ws 注入成功 |
| 4 | WebSocket 连接 Gateway | 握手成功 |
| 5 | 登录/进服 | GameServer 路由可达（若已启 DevStack） |

---

## 11. 生产部署要点

### 11.1 进程守护

- Windows：NSSM / 任务计划程序运行 `run_admin_5003.ps1`
- Linux：`systemd` + `waitress` 或 `gunicorn`（需适配入口）

### 11.2 反向代理

Nginx 示例思路：

- `https://portal.example.com` → `127.0.0.1:5003`
- WebSocket 升级头转发到 Gateway（若 Gateway 独立端口）

### 11.3 密钥与数据

- 轮换 `SECRET_KEY` / session 密钥
- PostgreSQL：`DATABASE_URL=postgresql://...`
- 定期备份 `data/` 与数据库

### 11.4 框架隔离

生产若**仅**拓扑：

```bash
export PORTAL_SERVER_FRAMEWORKS=topology
```

避免误暴露 BaaS 公共 API。

---

## 12. 故障排查

| 症状 | 可能原因 | 处理 |
|------|----------|------|
| `:5003` 被占用 | 旧 Portal 未退出 | `scripts\Stop-Portal5003.ps1` 后重启 |
| bootstrap 503 | `PORTAL_SERVER_FRAMEWORKS` 不含 topology | 设为 `topology` 或 `all` |
| gateway_ws 为空 | 拓扑未绑定 / 项目 env 错误 | Portal 服务器管理检查绑定 |
| Unity 编译失败 | 未导入拓扑模块 | 执行第 9 节导入 |
| 中文乱码 | 文件编码非 UTF-8 | 运行 `py scripts/encoding_gate.py` |

---

## 13. 相关文档

- [topology_server_deploy.md](./topology_server_deploy.md) — 速查
- [deploy_architecture.md](./deploy_architecture.md) — 四模块总览
- [topology_binding_architecture.md](../design_specs/topology_binding_architecture.md)

---

## 14. 验收签字表（自行勾选）

- [ ] Python 依赖安装完成
- [ ] `init_db()` 成功
- [ ] Portal :5003 health 200
- [ ] 拓扑项目创建且 server_mode 正确
- [ ] client-bootstrap / runtime-bootstrap 200
- [ ] 客户端拓扑模块 ZIP 已导入且编译通过
- [ ] WebSocket Gateway 连通（如适用）

全部勾选即拓扑服务器 + 客户端模块部署完成。
