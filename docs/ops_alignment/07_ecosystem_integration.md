# 生态全链路对齐：Agent 管控 × 拓扑编排 × game-server

更新时间：2026-06-06

## 单一事实来源（拓扑驱动）

| 层级 | 来源 | 关键字段 |
|------|------|----------|
| **设计/编辑 SoT** | apk-site 拓扑编排工作区 | `preset_id`, `role`, `daemon_*`, `ui.remote.port` |
| **Node Contract** | [`node_contract_registry.json`](node_contract_registry.json) | `cluster_type`, `default_port`, `probe_strategy`, Daemon 默认命令 |
| **运行时 SoT** | `game-server/config/cluster.json` | 由拓扑 **保存** 经 `POST /ops/topology/apply` 写入 |
| 节点凭证 | apk-site nodes 配置 | `ops_write_key=ops-write-key-2026`, `ops_base_url=http://127.0.0.1:5504` |
| Agent 身份 | `agent-{ServerId}` | `node_id=ServerId`, `project_id=GomeKu` |

**写路径**：`POST /api/ops-platform/topology/save` → 校验 Node Contract → upsert agents → `_sync_topology_to_game_server` → game-server 持久化 cluster.json。

**读路径**：`POST /api/ops-platform/cluster/sync` 仅 merge cluster 节点到画布（`meta.cluster_source=true`），**保留**用户添加的 infra 节点。

## 10 种节点类型对照

| Preset | Role | cluster Type | 探活 |
|--------|------|--------------|------|
| gateway_http | gateway | Gateway | tcp |
| auth_service | auth | Auth | cluster_embedded |
| business_main | business | Game | cluster_embedded |
| ops_service | ops | Ops | tcp |
| tcp_transport | transport | Tcp | tcp |
| redis_cache | cache | Daemon | redis_ping |
| mongo_db | database | Daemon | mongo_ping |
| mq_kafka | mq | Daemon | kafka_tcp |
| scheduler_job | scheduler | Daemon | tcp |
| pressure_worker | pressure | Daemon | tcp |

MySQL 模板已移除；GomeKu 主库为 MongoDB（`mongo_db`）。

## 路径对齐（macOS）

```bash
export GAME_SERVER_REPO="/Users/wangling/Desktop/MyGame/GameClient/game-server"
```

## 端口对齐（GomeKu cluster 基线）

| node_id | 角色 | 探测端口 |
|---------|------|----------|
| gateway-cn-1 | gateway | 15050 |
| auth-cn-1 | auth | embedded（/ops/cluster） |
| game-cn-1 | business | embedded（/ops/cluster） |
| ops-cn-1 | ops | 5504 |
| tcp-cn-1 | transport | 5601 |

Infra（Redis/Mongo/MQ 等）端口由 Node Contract `default_port` + 拓扑检查器配置。

## 启动顺序

```bash
# 1. 依赖
brew services start redis   # :6379
# MongoDB :27017 需已运行

# 2. game-server 集群
cd "$GAME_SERVER_REPO"
bash scripts/Start-GameServer.sh

# 3. apk-site（:5003）
cd /Users/wangling/Desktop/apk-site
python3 portals/common/core/app_new.py --port 5003

# 4. Agent 拉取循环
python3 tools/ecosystem_supervisor.py --daemon

# 5. 全链路验证
export OPS_USERNAME=admin OPS_PASSWORD=123456
python3 tools/ops_ecosystem_chain.py

# 6. 可选：full_framework 蓝图 → cluster.json 导出验证
python3 tools/ops_ecosystem_chain.py --full-framework
```

## cluster/sync 行为（merge）

`POST /api/ops-platform/cluster/sync` 会：

1. **Agent Registry** — upsert `agent-{ServerId}`
2. **Nodes 配置** — 同步 `ops_base_url` 等凭证
3. **拓扑画布 merge** — cluster 节点 upsert（保留非 `cluster_source` 的用户节点与边）

## apk-site 登录

- 默认：`admin` / `123456`
- 环境变量：`OPS_USERNAME`、`OPS_PASSWORD`

## game-server 本地启动

- 推荐：`--servers=gateway-cn-1,auth-cn-1,game-cn-1,ops-cn-1,tcp-cn-1 --headless`（常驻，仅 Web 停止/重启或崩溃时退出；冒烟测试可仍用 `--headless-seconds=N`）
- `ServerModuleFactory` 将 `Cache/Db/Mq/Scheduler/Pressure/Admin` 别名归一为 `Daemon`
- `ServerNodeConfig.ProbeHost` 用于探活地址（fallback `Host`）

## API 对齐

### 拓扑写入

- `POST /api/ops-platform/topology/save` — 校验 + 写 cluster
- `POST /api/ops-platform/topology/apply-blueprint` — 应用蓝图（需再 save 推送 cluster）
- `POST /api/ops-platform/node/add-from-preset` — scoped 拓扑写入

### game-server Ops API

- `POST /ops/topology/apply` — 接收 cluster payload，`Type` 归一化为 `Daemon`（infra）

## 绑定门禁

1. `node_id` 与 cluster `ServerId` 一致
2. Agent probe PASS（infra 支持 redis_ping / cluster_embedded）
3. 心跳 120s 内有效
4. `project_id=GomeKu`
