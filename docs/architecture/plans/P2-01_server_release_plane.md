# P2-01：Server Release Plane（服务端发布）

| 项 | 值 |
|----|-----|
| 优先级 | P2 |
| 预估 | 4–8 周 |
| 依赖 | P1-01, P1-05 |
| 评审项 | game-server 与 ReleaseOrder 断裂 |
| 状态 | **Done**（Portal MVP，2026-07-28） |

---

## 1. 目标

引入 **Server Release Order**，与 Client ReleaseOrder 关联同一 Release Ticket：

- 服务端制品版本化
- Ops Agent 滚动部署
- publish 前 gate：client + server + protocol 兼容

---

## 2. 范围（本迭代交付）

**In（Portal）**

- [x] `server_artifacts` / `server_release_orders` SQLite 表
- [x] Artifact 登记 API（path + multipart）
- [x] Server release CRUD + 状态机
- [x] `deploy_server_artifact` Agent job 入队
- [x] Client precheck 联合 gate
- [x] Journey 展示 server_release_gate
- [x] `docs/runbooks/server_release.md`

**Out（后续 / game-server 仓库 — 永久不在 Portal MVP）**

- ServerAgent `deploy_server_artifact` 完整实现
- Jenkins `GameServer-Build` job
- K8s operator
- **config 热更 Step 5（GAP-P2-01-S5-01）**：Portal MVP 不交付；游戏服侧配置推送与滚动热更留在 game-server 仓库后续迭代。关闭口径：**书面 Out**，非 DEFERRED 吞单。

---

## 3. 分步实施

### Step 1：Artifact 上传与登记 ✅

- `POST /api/admin/projects/{id}/server-artifacts`
- 存储：`data/server_artifacts/{project_id}/`

### Step 2：Server Release 状态机 ✅

- `services/release/server_release_service.py`
- pytest `test_server_release.py`

### Step 3：Agent Deploy Job ✅（Portal 侧）

- `services/ops/server_deploy_dispatch.py`
- `POST .../server-releases/{id}/deploy`
- `POST .../complete-deploy`（Agent 回调占位）

### Step 4：与 Client ReleaseOrder 关联 ✅

- payload: `server_release_id`, `min_server_version`, `waive_server_release_check`
- `precheck_release_order` 联合 gate

### Step 5：config 热更 — Out（Portal MVP）

- **不做**：Portal 不提供服配置热更 API/UI；与 `OPEN_ITEMS_MASTER` 项 `GAP-P2-01-S5-01` 对齐为产品面 **Out**。
- 游戏服仓库若需热更，单独 Plan；与本 Portal 发布单状态机无耦合。

---

## 4. 完成定义（DoD）

- [x] Portal MVP：artifact + server release + deploy 入队 + precheck gate
- [x] runbook 已提交
- [x] DevStack 端到端 demo（证据 [`docs/evidence/2026-11-09/GAP-P2-01-E2E-01.json`](../../evidence/2026-11-09/GAP-P2-01-E2E-01.json)）
- [x] 评审「服务端发布 gap」Portal 侧关闭
