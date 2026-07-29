# Server Release Runbook（P2-01）

服务端发布平面：与 Client ReleaseOrder **关联同一发布窗口**，通过 Ops Agent 滚动部署 game-server 制品。

---

## 前置

| 项 | 说明 |
|----|------|
| P1-05 | `infra_nodes` 已登记 Runtime 节点 |
| Agent | ServerAgent 支持 `deploy_server_artifact` 命令（game-server 仓库） |
| 拓扑 | 已知 `topology_id` 与 `target_services`（如 `game-cn-1`, `gateway-cn-1`） |

---

## 流程概览

1. **登记制品** → `POST /api/admin/projects/{id}/server-artifacts`
2. **创建 Server Release** → `POST /api/admin/projects/{id}/server-releases`
3. **部署** → `POST .../server-releases/{id}/deploy`（队列 Agent job）
4. **确认完成** → Agent 回调或 `POST .../complete-deploy`
5. **关联 Client ReleaseOrder** → payload 填 `server_release_id` + 可选 `min_server_version`
6. **Client precheck** → 联合 gate：production/staging 要求 server deployed

---

## API 示例

### 登记制品（Jenkins 回调 / path 引用）

```http
POST /api/admin/projects/GomeKu/server-artifacts
Content-Type: application/json

{
  "version_label": "1.0.1",
  "protocol_version": "v1",
  "bundle_path": "E:/artifacts/gameserver-1.0.1.zip",
  "checksum": "sha256:..."
}
```

multipart 上传：字段名 `bundle`，JSON 元数据同 body。

### 创建 Server Release

```http
POST /api/admin/projects/GomeKu/server-releases
Content-Type: application/json

{
  "env_key": "development",
  "topology_id": "topo-dev-1",
  "artifact_id": "sart-xxxx",
  "target_services": ["game-cn-1", "auth-cn-1"]
}
```

状态：`draft`（无 artifact）→ `ready`（有 artifact）→ `deploying` → `deployed` / `failed`

### 部署

```http
POST /api/admin/projects/GomeKu/server-releases/{server_release_id}/deploy
```

Portal 为每个 `target_service` 入队 `deploy_server_artifact` Agent job。

### 关联 Client ReleaseOrder

编辑发布计划 payload：

```json
{
  "server_release_id": "sro-xxxx",
  "min_server_version": "1.0.1",
  "waive_server_release_check": false,
  "deploy_server_with_client": false
}
```

- **production / staging**：未部署 → precheck **阻断**
- **development**：未部署 → **warning** 不单独阻断

---

## 回滚

```http
POST /api/admin/projects/GomeKu/server-releases/{id}/rollback
Content-Type: application/json

{ "previous_artifact_id": "sart-prev" }
```

---

## Dev 联合发布 Demo 清单

1. 登记 server artifact（zip）
2. 创建 + deploy server release → `deployed`
3. Client ReleaseOrder payload 填 `server_release_id`
4. Client precheck → `server_release_gate.ok=true`
5. Client publish + verify

---

## 相关 Plan

- `docs/architecture/plans/P2-01_server_release_plane.md`
- `docs/architecture/plans/P1-05_node_registry_unification.md`
