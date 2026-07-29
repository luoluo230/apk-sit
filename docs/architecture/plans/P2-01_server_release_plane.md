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

**Out（后续 / game-server 仓库）**

- ServerAgent `deploy_server_artifact` 完整实现
- Jenkins `GameServer-Build` job
- K8s operator
- config 热更 Step 5

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

### Step 5：config 热更 ⏸

- 留待后续

---

## 4. 完成定义（DoD）

- [x] Portal MVP：artifact + server release + deploy 入队 + precheck gate
- [x] runbook 已提交
- [ ] DevStack 端到端 demo（需 game-server Agent 实现）
- [x] 评审「服务端发布 gap」Portal 侧关闭
