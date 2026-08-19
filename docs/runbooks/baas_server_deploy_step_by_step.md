# 轻度 Casual BaaS 服务器 — 逐步部署教程（完整版）

> 架构标识：`casual_baas_server`  
> 配套客户端包：`dist/client-network-baas-*.zip`  
> 默认地址：`http://127.0.0.1:5004`  
> Bootstrap：`GET /api/public/client-bootstrap`（兼容 `/api/public/baas-bootstrap`）

---

## 0. 你将得到什么

| 组件 | 说明 |
|------|------|
| 独立 BaaS Portal | REST 游戏 API + GM 运维台 |
| 房间/PVP MVP | guest 登录、匹配、帧同步 fan-out |
| SQLite / PostgreSQL | 开发默认 SQLite；生产可选 Postgres |
| 部署压缩包 | `dist/baas-server-architecture.zip` |
| 客户端 BaaS 模块 | 独立 ZIP，导入后启用 `MAClient.Network.Baas` |

**不包含**：拓扑 Agent/GameServer WebSocket 栈（与中重度完全解耦）。

---

## 1. 环境准备

### 1.1 必装

| 软件 | 验证 |
|------|------|
| Git | `git --version` |
| Python 3.10–3.12 | `py -3 --version` |
| PowerShell 5.1+ | `$PSVersionTable.PSVersion` |

### 1.2 可选（生产数据库）

| 软件 | 用途 |
|------|------|
| Docker Desktop | 运行 `docker-compose.baas.yml` 中的 PostgreSQL |

### 1.3 端口

| 端口 | 服务 |
|------|------|
| 5004 | BaaS Portal HTTP |
| 5433 | PostgreSQL（docker-compose 映射，可选） |

---

## 2. 获取代码与部署包

### 2.1 克隆仓库

```powershell
cd E:\
git clone https://github.com/luoluo230/apk-sit.git apk-site
cd E:\apk-site
git checkout newVersion
```

### 2.2 合并 BaaS 架构部署包

```powershell
Expand-Archive -Path E:\releases\baas-server-architecture.zip -DestinationPath E:\apk-site -Force
```

合并后关键路径：

```
scripts/Start-BaaSStack.ps1
scripts/Export-ClientNetworkModule.ps1
scripts/Import-ClientNetworkModule.ps1
docker-compose.baas.yml
portals/common/core/app_baas.py
portals/common/core/routes/baas/
portals/common/core/services/baas/
packages/client_network/baas/
docs/runbooks/baas_server_deploy_step_by_step.md
manifest.json
```

### 2.3 确认 manifest

```powershell
(Get-Content E:\apk-site\manifest.json | ConvertFrom-Json).architecture
# 期望: casual_baas_server
```

---

## 3. 安装 Python 依赖

```powershell
cd E:\apk-site\portals\common\core
py -3 -m venv venv
.\venv\Scripts\Activate.ps1
pip install -r requirements-prod.txt
pip install waitress
```

BaaS standalone 入口使用 `waitress` 提供 WSGI 服务（见 `scripts/run_baas_server.ps1`）。

---

## 4. 环境变量说明

| 变量 | 默认值 | 含义 |
|------|--------|------|
| `BAAS_STANDALONE` | `1` | 独立模式，不加载拓扑 Ops |
| `PORTAL_SERVER_FRAMEWORKS` | `baas` | 仅注册 BaaS 框架 |
| `BAAS_PORT` | `5004` | 监听端口 |
| `BAAS_HOST` | `127.0.0.1` | 绑定地址 |
| `DATABASE_URL` | （空=SQLite） | PostgreSQL 连接串 |
| `APP_PORTAL_MODE` | `admin` | 管理端模式 |

PowerShell 临时设置：

```powershell
$env:BAAS_STANDALONE = "1"
$env:PORTAL_SERVER_FRAMEWORKS = "baas"
$env:BAAS_PORT = "5004"
```

---

## 5. 数据库初始化

### 5.1 SQLite（默认，零配置）

数据文件：`E:\apk-site\data\apk_site.db`（或 core 相对路径）

```powershell
cd E:\apk-site\portals\common\core
py -3 -c "from models.db import init_db; init_db(); print('init_db OK')"
```

自动创建 `baas_services`、`baas_players`、`baas_rooms` 等表（见 `baas_migrations`）。

### 5.2 PostgreSQL（生产推荐）

**步骤 1** — 启动 Postgres 容器：

```powershell
cd E:\apk-site
docker compose -f docker-compose.baas.yml up -d postgres
docker compose -f docker-compose.baas.yml ps
```

**步骤 2** — 设置连接串（注意宿主机端口 **5433**）：

```powershell
$env:DATABASE_URL = "postgresql://apk_baas:apk_baas_dev@127.0.0.1:5433/apk_baas"
```

**步骤 3** — 再次 `init_db()`（同上）。

---

## 6. 启动 BaaS 服务

### 6.1 一键启动（推荐）

```powershell
cd E:\apk-site
powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1 -Background
```

带 PostgreSQL：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1 -UsePostgres -Background
```

脚本内部顺序：

1. 设置 `BAAS_STANDALONE` / `PORTAL_SERVER_FRAMEWORKS`
2. （可选）docker compose 起 Postgres
3. `init_db()`
4. 后台启动 `run_baas_server.ps1`
5. 轮询 `http://127.0.0.1:5004/health` 最多 90 秒

### 6.2 前台调试启动

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Start-BaaSStack.ps1
# Ctrl+C 停止
```

### 6.3 手动启动（等价）

```powershell
cd E:\apk-site\portals\common\core
$env:BAAS_STANDALONE = "1"
$env:PORTAL_SERVER_FRAMEWORKS = "baas"
py -3 -m waitress --listen=127.0.0.1:5004 app_baas:app
```

---

## 7. 验证服务健康

```powershell
Invoke-WebRequest -Uri http://127.0.0.1:5004/health -UseBasicParsing
```

期望 JSON 含 `"ok": true`, `"framework": "casual_baas"` 或类似字段。

### 7.1 管理入口

| URL | 说明 |
|-----|------|
| http://127.0.0.1:5004/login | 管理员登录 |
| http://127.0.0.1:5004/admin/baas | BaaS 首页 |
| http://127.0.0.1:5004/admin/projects/{id}/baas-gm/{service_id} | GM 运维台 |

---

## 8. 创建 BaaS 项目与服务

### 8.1 通过 Portal UI

1. 登录 `:5004`
2. **新建项目** → `server_mode` 选择 **casual_baas** / 轻度
3. 在 **Casual 服务** 中创建 BaaS Service
4. 记录：
   - `project_id`
   - `service_id`（UUID）
   - **API Key / Secret**（公共 REST 鉴权）

### 8.2 通过 seed 脚本（自动化/E2E）

```powershell
cd E:\apk-site\portals\common\core
py -3 scripts/seed_baas_playmode_e2e.py
```

凭据写入 `docs/evidence/baas-playmode-e2e-credentials.json`（**勿提交 Git**）。

---

## 9. 公共 API 与 Bootstrap 验证

### 9.1 client-bootstrap

```powershell
$base = "http://127.0.0.1:5004"
$q = "game_id=YOUR_GAME&game_key=YOUR_KEY&env_key=dev&channel=wechat&platform=android"
Invoke-WebRequest -Uri "$base/api/public/client-bootstrap?$q" -UseBasicParsing
```

或 legacy：

```powershell
Invoke-WebRequest -Uri "$base/api/public/baas-bootstrap?$q" -UseBasicParsing
```

响应 `data` 中应含 `public_api_base`、`service_id`、鉴权头名称。

### 9.2 REST API 示例（guest 登录）

```powershell
$headers = @{
  "X-BaaS-Service" = "<service_id>"
  "X-BaaS-Key"     = "<api_secret>"
}
Invoke-WebRequest -Uri "http://127.0.0.1:5004/api/baas/v1/<service_id>/guest/login" `
  -Method POST -Headers $headers -Body '{"device_id":"test-device-1"}' `
  -ContentType "application/json" -UseBasicParsing
```

### 9.3 PVP 房间 fan-out E2E（服务端）

```powershell
cd E:\apk-site\portals\common\core
py -3 scripts/run_baas_pvp_fanout_e2e.py --portal http://127.0.0.1:5004
```

全绿即 room match / push_frame / poll_frames 正常。

---

## 10. GM 运维能力速查

| 功能 | 方法 | 路径模式 |
|------|------|----------|
| 仪表盘 | GET | `.../gm/dashboard` |
| 玩家列表 | GET | `.../gm/players` |
| 全服邮件 | POST | `.../gm/mail/broadcast` |
| 钱包调整 | POST | `.../gm/wallet` |
| 礼包码 | GET/POST | `.../gm/gift-codes` |
| 排行榜 | GET/DELETE | `.../gm/leaderboards/{board_id}` |
| PVP 房间 | GET | GM 控制台 rooms 面板 |

浏览器：`/admin/projects/{project_id}/baas-gm/{service_id}`

---

## 11. 导入客户端 BaaS 网络模块

基础 Unity 工程**不应**包含 `Assets/Modules/BaasNetwork`（仅保留 Abstractions Gate）。

### 11.1 解压

```powershell
Expand-Archive E:\apk-site\dist\client-network-baas-*.zip E:\tmp\baas-module -Force
```

### 11.2 导入

```powershell
cd E:\apk-site
powershell -ExecutionPolicy Bypass -File scripts\Import-ClientNetworkModule.ps1 `
  -Module baas `
  -MaclientRoot E:\maclient `
  -SourceDir E:\tmp\baas-module\ClientNetworkModule
```

写入 `Assets/StreamingAssets/client_network_modules.json` 中 `baas.installed=true`。

### 11.3 Unity 侧 API

| 类 | 用途 |
|----|------|
| `BaasNetworkModule` | Bootstrap + 公共 API 基址 |
| `BaasRoomClient` | PVP：matchmake / push_frame / poll_frames / finish |
| `BaasHttp` | REST 封装 |

命名空间：`MAClient.Network.Baas`

### 11.4 PlayMode E2E（可选）

```powershell
$env:BAAS_E2E_PORTAL = "http://127.0.0.1:5004"
$env:BAAS_E2E_SERVICE_ID = "<from credentials>"
$env:BAAS_E2E_API_KEY = "<from credentials>"
cd E:\apk-site\portals\common\core
py -3 scripts/run_baas_playmode_e2e.py --skip-server
```

---

## 12. 生产部署清单

- [ ] `DATABASE_URL` 指向托管 PostgreSQL
- [ ] 修改 docker-compose 默认密码
- [ ] HTTPS 终止于 Nginx/Caddy
- [ ] API Key 轮换策略
- [ ] `docs/design_specs/casual_baas_pvp_mvp_boundary.md` 中 MVP 边界已评审
- [ ] 日志采集（Portal logging 配置）
- [ ] 备份 `baas_*` 表

### 12.1 systemd 示例思路（Linux）

```ini
[Service]
Environment=BAAS_STANDALONE=1
Environment=PORTAL_SERVER_FRAMEWORKS=baas
Environment=DATABASE_URL=postgresql://...
WorkingDirectory=/opt/apk-site/portals/common/core
ExecStart=/opt/apk-site/portals/common/core/venv/bin/python -m waitress --listen=0.0.0.0:5004 app_baas:app
```

---

## 13. 故障排查

| 症状 | 原因 | 处理 |
|------|------|------|
| health 超时 | 端口占用 / Python 异常 | 查 `run_baas_server.ps1` 窗口日志 |
| bootstrap 503 | `PORTAL_SERVER_FRAMEWORKS` 非 baas | 设为 `baas` |
| API 401 | Service/Key 错误 | Portal 项目设置核对 |
| poll_frames 空 | 房间未 start / seq 不对 | 跑 `run_baas_pvp_fanout_e2e.py` 对比 |
| Postgres 连接失败 | 端口/密码 | `docker compose logs postgres` |

---

## 14. 与中重度拓扑共存

同一台机器可同时运行：

- 拓扑 Portal `:5003`（`PORTAL_SERVER_FRAMEWORKS=topology` 或 `all`）
- BaaS Portal `:5004`（`Start-BaaSStack.ps1`）

**客户端**：同一 Unity 工程不要同时导入 topology + baas 模块，除非明确做双栈；用 `ClientNetworkModuleGate` 检测。

---

## 15. 相关文档

- [baas_standalone_deploy.md](./baas_standalone_deploy.md)
- [casual_baas_pvp_mvp_boundary.md](../design_specs/casual_baas_pvp_mvp_boundary.md)
- [casual_baas_services.md](../design_specs/casual_baas_services.md)

---

## 16. 验收签字表

- [ ] `Start-BaaSStack.ps1 -Background` 成功
- [ ] `/health` 200
- [ ] BaaS 项目 + Service + API Key 已创建
- [ ] client-bootstrap 200
- [ ] guest login REST 200
- [ ] `run_baas_pvp_fanout_e2e.py` PASS
- [ ] 客户端 baas ZIP 已导入且编译通过
- [ ] （可选）PlayMode E2E PASS

全部勾选即 BaaS 服务器 + 客户端模块部署完成。
