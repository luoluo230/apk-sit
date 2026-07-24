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

1. 删除模块级 `projects_db = load_document(...)` 可变全局；改为 `@lru_cache` **仅只读 snapshot** 或每次 `project_repo.get` 读 DB。
2. 批量替换：`grep projects_db` 的 40+ 引用 → `project_repo.get/list`。
3. 写路径统一 `project_repo.save` → 失效 cache / 无 cache。

**改文件**

- `data/projects.py`, `data/channels.py`, `data/versions.py`
- `services/admin/project_service.py`
- `services/release/*.py`, `services/ops/*.py`, `routes/admin_routes.py`

**验收**

- [ ] 进程 A 写项目，进程 B（第二 waitress worker 或 subprocess）立即可读
- [ ] pytest `tests/test_users_data.py` 等 admin 测试 pass

---

### Step 3：SQLite 连接池化（2 天）

**动作**

1. `db.py`：`_get_conn()` 改为 **thread-local 连接** 或 `sqlite3.connect` per `get_cursor()` context（WAL 模式保留）。
2. 移除「全局单 `_conn` + RLock」；文档注释 SIGSEGV 根因已修复。
3. 可选：连接 `timeout=30` 保持。

**改文件**

- `portals/common/core/models/db.py`

**验收**

- [ ] 并发 pytest stress（10 thread 写 release_order）无 database locked 超时
- [ ] 无 exit 139 回归

---

### Step 4：Ops 存储并入主库（3 天）

**动作**

1. 默认 `OPS_USE_SQLITE=true` 且 **与 `apk_site.db` 同文件**（或同 Postgres DB 不同 schema）。
2. 迁移脚本扩展 `scripts/migrate_ops_json_to_sqlite.py` → 写入主库 `ops_*` 表。
3. `services/ops/storage.py` 读 `Config.USE_SQLITE` 单一开关。

**改文件**

- `portals/common/core/services/ops/storage.py`
- `portals/common/core/config.py`
- migration script

**验收**

- [ ] Ops 拓扑/Agent 与 Release 同一 backup 命令可备份
- [ ] `tests/test_ops_runtime_service.py` pass

---

### Step 5：Scope / Platform migration 补全（2 天）

**动作**

1. `db.py` `_bundle_platform` / `_migrate_release_scopes_platform` 扩展：
   - 合法 platform：`android`, `ios`, `wechat_minigame`（读 `platforms.VALID_PLATFORMS`）
2. 启动 `init_db()` 时跑 migration version 表，避免重复迁移。
3. `scope_ids.py` 输入归一：`stage`→`env_key` 仅入口层，DB 只存 `env_key`。

**改文件**

- `portals/common/core/models/db.py`
- `portals/common/core/services/release/scope_ids.py`
- `portals/common/core/tests/test_scope_resolver.py` — 新增 wechat_minigame case

**验收**

- [ ] scope_id 四段含 `wechat_minigame` 可 create + publish
- [ ] 旧三段 scope 迁移脚本 idempotent

---

### Step 6：PostgreSQL 轨（可选，5 天）

**动作**

1. 新增 `DATABASE_URL` env；`db.py` 工厂：`sqlite` | `postgres`（SQLAlchemy 或 psycopg3 薄封装）。
2. `docker-compose.postgres.yml`：postgres:16 + portal 单实例。
3. 迁移工具：`scripts/migrate_sqlite_to_postgres.py`（projects/channels/versions + release_* + ops_*）。

**验收**

- [ ] 本地 compose 起 Portal，pytest 全 pass 对 Postgres
- [ ] 文档 `docs/runbooks/postgres_migration.md`

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

- [ ] Step 1–5 验收全勾（Step 6 按部署需求）
- [ ] 无模块级可变 `projects_db` 全局
- [ ] backup runbook（P0-01 Step 6）已含 DB 单一真源说明
- [ ] P1-02 Onboarding / P1-05 Node Registry 可依赖本 Plan 的 repo API
