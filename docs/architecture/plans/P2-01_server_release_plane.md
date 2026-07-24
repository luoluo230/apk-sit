# P2-01：Server Release Plane（服务端发布）

| 项 | 值 |
|----|-----|
| 优先级 | P2 |
| 预估 | 4–8 周 |
| 依赖 | P1-01, P1-05 |
| 评审项 | game-server 与 ReleaseOrder 断裂 |

---

## 1. 目标

在 **不合并 Delivery 与 Ops 代码库** 的前提下，引入 **Server Release Order**，与 Client ReleaseOrder **关联同一 Release Ticket**，实现：

- 服务端制品（zip/exe/docker）版本化
- 通过 Ops Agent 滚动重启 / 配置热更
- publish 前 gate：client bundle + server artifact + protocol 版本兼容

---

## 2. 范围

**In**

- 数据模型：`server_release_orders`, `server_artifacts`
- API：创建 / 部署 / 回滚 server release
- Agent job：deploy game-server bundle
- ReleaseOrder 扩展字段 `linked_server_release_id`（可选）
- 联合 precheck：gateway 可达 + server version ≥ min

**Out**

- K8s operator 全量实现（Phase 2 仅 Agent + 二进制 zip）
- 数据库 schema 自动迁移（Mongo migration 仍手工）

---

## 3. 数据模型

```sql
CREATE TABLE server_release_orders (
  server_release_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  env_key TEXT NOT NULL,
  topology_id TEXT NOT NULL,
  artifact_id TEXT,
  status TEXT NOT NULL,  -- draft|building|ready|deploying|deployed|failed|rolled_back
  target_services JSON,  -- ["game-cn-1","auth-cn-1"]
  payload JSON,
  created_by TEXT,
  created_at TEXT,
  updated_at TEXT
);

CREATE TABLE server_artifacts (
  artifact_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  version_label TEXT,
  bundle_path TEXT,
  checksum TEXT,
  protocol_version TEXT,
  payload JSON,
  created_at TEXT
);
```

---

## 4. 分步实施

### Step 1：Artifact 上传与登记（1 周）

**动作**

1. `POST /api/admin/projects/{id}/server-artifacts` — multipart 或 path 引用（Jenkins 回调）
2. Jenkins 新 job `GameServer-Build`（可选，MSBuild `game-server.sln`）
3. 存储：local `data/server_artifacts/` + OSS mirror

**验收**

- [ ] 上传 zip → artifact 记录可查询

---

### Step 2：Server Release 状态机（1 周）

**动作**

1. `services/release/server_release_service.py` — CRUD + transition
2. 状态：draft → ready → deploying → deployed
3. 单元测试 mirror client release 测试风格

**验收**

- [ ] pytest server release transitions

---

### Step 3：Agent Deploy Job（2 周）

**动作**

1. ServerAgent 新 command：`deploy_server_artifact`
   - stop services（rolling）
   - 解压到 staging
   - 替换 binary + 重启
2. Portal `POST .../server-releases/{id}/deploy` → 队列 Agent job
3. 进度 SSE / poll

**改文件**

- `maclient/game-server/tools/ServerAgent/`
- `portals/common/core/services/ops/agent_dispatch.py`（或等价）

**验收**

- [ ] DevStack：deploy 新 game-server build → Gateway 仍可达
- [ ] 失败 rollback 至上一 artifact

---

### Step 4：与 Client ReleaseOrder 关联（1 周）

**动作**

1. ReleaseOrder payload 增加 `server_release_id` / `min_server_version`
2. `precheck_release_order`：若关联 server release，检查 deployed 版本
3. Journey UI：可选「同时部署服务端」checkbox（development 默认 off）

**验收**

- [ ] 联合发布单：client publish 前 server deployed 或 explicit waive

---

### Step 5：game-server 配置热更（可选，1 周）

**动作**

1. 非 binary 变更：`config/cluster.json` patch via Ops API
2. `catalog_reload_url` 已有 pattern 扩展 server config reload

---

## 5. 大厂对齐说明

| 能力 | 腾讯 | 本项目 Step |
|------|------|-------------|
| 客户端/服务端同单 | 同一 TAPD 发布单多 artifact | Step 4 linked id |
| 服务端 rolling | K8s rollout | Step 3 Agent rolling |
| 协议 gate | 强制匹配 | min_server_version precheck |

---

## 6. 完成定义（DoD）

- [ ] Dev 环境完成一次 client + server 联合发布 demo
- [ ] runbook `docs/runbooks/server_release.md`
- [ ] 评审「服务端发布 gap」关闭
