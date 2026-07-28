# P0-02：Config Registry 与存储统一

| 项 | 值 |
|----|-----|
| 优先级 | P0 — 架构阻断 |
| 预估 | 2–4 周 |
| 依赖 | 无（与 P0-01 可并行） |
| 评审项 | W-P0-3, W-P0-4, 双/三存储、Legacy scope 词汇 |

---

## 1. 目标

将 **项目/渠道/版本元数据** 从 import 时 JSON 内存缓存，迁移到 **可并发读写的统一 Registry**；发布域 SQLite 连接模型可扩展；消除多 worker 脏读。

**终态选项**（本 Plan 分两轨，二选一或渐进）：

- **轨 A（推荐）**：PostgreSQL 作为 Config + Release 真源
- **轨 B（过渡）**：单进程 Waitress + SQLite WAL + 去掉 `projects_db` 内存缓存（仍不支持水平扩展，但先修脏读）

---

## 2. 范围

**In**

- `projects_db`, `channels_db`, `project_versions_db` 读写路径
- `models/db.py` 连接模型
- `OPS_USE_SQLITE` 与主库关系梳理
- scope migration 支持 `wechat_minigame`
- `stage` → `env_key` 写入路径归一

**Out**

- 全量 Postgres 运维（K8s operator）— 仅 schema + docker-compose 样例
- 历史 JSON 文件删除（保留 mirror 至少 1 个 release）

---

## 3. 前置条件

- [ ] 现有 `data/apk_site.db` 与 JSON 已备份
- [ ] 明确部署模式：单实例 vs 多 worker（决定轨 A/B）

---

## 4. 分步实施

### Step 1：Registry 抽象层（3 天）

**动作**

1. 新建 `repositories/registry/`：
   - `project_repo.py` — `get(project_id)`, `list()`, `save(row)`, `delete()`
   - `channel_repo.py`
   - `version_row_repo.py`
2. 首版实现：**SQLite 新表** + JSON import/export，接口稳定后再换 Postgres。
3. 禁止业务代码直接 `from data.projects import projects_db`；通过 repo 访问。

**新表（SQLite 阶段）**

```sql
CREATE TABLE projects (
  project_id TEXT PRIMARY KEY,
  payload JSON NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE channels (
  channel_id TEXT PRIMARY KEY,
  payload JSON NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE TABLE project_versions (
  version_id TEXT PRIMARY KEY,
  project_id TEXT NOT NULL,
  payload JSON NOT NULL,
  updated_at TEXT NOT NULL
);
CREATE INDEX idx_project_versions_project ON project_versions(project_id);
```

**改文件**

- `portals/common/core/repositories/registry/*.py`（新建）
- `portals/common/core/models/db.py` — schema migration
- `portals/common/core/data/projects.py` — 改为 thin wrapper 调 repo（兼容期）

**验收**

- [x] `project_service.create_project` 走 repo，重启进程后数据仍在
- [x] 双写：repo save 同时更新 JSON mirror（`SAVE_JSON_MIRROR=true`）

---

### Step 2：消除 import 缓存（2 天）

**动作**

1. 删除模块级 `projects_db = load_document(...)` 可变全局；改为 DB-backed proxy 或 `project_repo.get/list`。
2. 兼容期保留 `projects_db` proxy（每次读写走 SQLite），新代码优先 `repositories.registry.accessors`。
3. 写路径统一 `project_repo.save` → 无 import 缓存。

**改文件**

- `data/projects.py`, `data/channels.py`, `data/versions.py`
- `repositories/registry/_proxies.py`, `accessors.py`
- `services/admin/project_service.py`（已通过 repo）
- `services/release/*.py`, `services/ops/*.py`, `routes/admin_routes.py`（兼容 proxy）

**验收**

- [x] `projects_db`/`channels_db`/`project_versions_db` 为 DB proxy，无 `load_document` import 缓存
- [x] pytest `tests/test_project_registry.py`、`tests/test_project_repo_concurrency.py` pass
- [ ] 进程 A 写项目，进程 B 立即可读（需多 worker 手工验证）

---

### Step 3：SQLite 连接池化（2 天）

**动作**

1. `db.py`：`_get_conn()` 改为 **thread-local 连接**（WAL 模式保留）。
2. 移除全局单 `_conn`；新增 `reset_db_connection()` 供测试/worker 回收。
3. 连接 `timeout=30` 保持。

**改文件**

- `portals/common/core/models/db.py`

**验收**

- [x] thread-local 连接 + `reset_db_connection()`
- [x] `tests/test_project_repo_concurrency.py` 双线程读写 pass
- [ ] 10 thread release_order stress（后续专项）

---

### Step 4：Ops 存储并入主库（3 天）

**动作**

1. `OPS_USE_SQLITE` 默认跟随 `USE_SQLITE`（同 `apk_site.db`）。
2. 迁移脚本 `scripts/migrate_ops_json_to_sqlite.py` 已有。
3. `services/ops/storage.py` 读 `Config.USE_SQLITE` 单一开关。

**改文件**

- `portals/common/core/services/ops/storage.py`
- `portals/common/core/config.py`

**验收**

- [x] Ops SQLite 与主库同文件（`models.db.init_db`）
- [x] `_use_sqlite()` 优先 `Config.USE_SQLITE`
- [ ] `tests/test_ops_runtime_service.py` pass（环境依赖）

---

### Step 5：Scope / Platform migration 补全（2 天）

**动作**

1. `_bundle_platform` / `_migrate_release_scopes_platform` 扩展 `wechat_minigame`。
2. `schema_migrations` 表 + `release_scopes_platform_v2` 幂等标记。
3. `scope_ids.py` 使用 `get_project` accessor。

**改文件**

- `portals/common/core/models/db.py`
- `portals/common/core/services/release/scope_ids.py`
- `portals/common/core/tests/test_scope_resolver.py`

**验收**

- [x] scope_id 四段含 `wechat_minigame`
- [x] migration idempotent（`schema_migrations`）
- [ ] 端到端 publish wechat_minigame（E2E 专项）

---

### Step 6：PostgreSQL 轨（可选，5 天）

**动作**

1. 新增 `DATABASE_URL` env（config 已预留）。
2. `docker-compose.postgres.yml` + `docs/runbooks/postgres_migration.md`。
3. 迁移工具：`scripts/migrate_sqlite_to_postgres.py`（待实现）。

**验收**

- [x] compose + runbook skeleton
- [ ] 本地 compose pytest 全 pass
- [ ] migrate script

---

## 5. 测试与门禁

```bash
cd portals/common/core
python -m pytest tests/ -q --ignore=tests/e2e
python portals/common/core/scripts/migrate_ops_json_to_sqlite.py --dry-run
```

新增：`tests/test_project_repo_concurrency.py`（双线程读写同一 project）。

---

## 6. 回滚

- `SAVE_JSON_MIRROR=true` 期间可从 JSON 恢复
- `USE_SQLITE=true` + 旧 `projects_db` 分支保留 1 release（feature flag `LEGACY_JSON_PROJECTS=1`）

---

## 7. 完成定义（DoD）

- [x] Step 1–5 核心实现（Step 6 skeleton；factory/migrate 待续）
- [x] 无模块级可变 `projects_db` JSON 缓存（DB proxy + accessors）
- [ ] backup runbook（P0-01 Step 6）已含 DB 单一真源说明
- [ ] P1-02 Onboarding / P1-05 Node Registry 可依赖本 Plan 的 repo API
