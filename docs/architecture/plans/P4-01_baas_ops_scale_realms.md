# P4-01：BaaS 可运维扩容与逻辑区服

| 字段 | 值 |
|------|-----|
| In | 创建项目 `server_mode` 选型与 UI 分流；BaaS 一键部署；Web 监听/GM；10 万日活容量骨架；逻辑区服/滚服/合服/多节点 |
| Out | iOS/微信真发；topology 区服模型（继续 Agent 平面） |
| 首交付 | Wave A |
| 区服模型 | 逻辑区服（多 API 水平扩展 + S1/S2…；合服=区数据迁移） |

## Wave 总览

| Wave | 目标 | 验收 |
|------|------|------|
| A | 选型分流 + 一键部署 + 监听/GM | 创建锁死 server_mode；导航互斥；bat 起栈 health=ok；GM 可操作 |
| B | 10 万+ 日活骨架 | 多 worker + Redis + Postgres 池；压测证据 |
| C | 逻辑区服/滚服/合服 | realms CRUD；选服 API；合服 job；节点心跳 |

## Wave A Steps

### A1 创建项目强制选服务器类型
- [x] 弹窗必选 topology / casual_baas
- [x] payload 传 `server_mode`；创建后锁定不可改

### A2 项目内只显示已选服务器相关信息
- [x] `project_nav_policy.visible_nav_item_ids` / `filter_shell_groups`
- [x] shell_nav / 服务器管理按 mode 过滤

### A3 一键部署
- [x] `Deploy-BaasOneClick.bat` → `scripts/Deploy-BaasOneClick.ps1`
- [x] 检测 Python/Git/Docker；写 `.env.baas.local`；起栈；打印 URL

### A4 Web 监听 + GM
- [x] BaaS 服务器管理：健康/DB/GM 入口 + 区服面板
- [x] `/health` + `/health/ready`

## 产品容量声明（2026-11-10）

**10 万日活 = 容量骨架 + 本机 smoke 仅**；`p4_01_baas_load_smoke.py` 与 `GAP-P4-01-*.json` 证明的是本地/开发栈骨架，**不构成**生产规模签字。生产容量与压测 sign-off **明确 OUT**，直至运维/容量评审完成。追踪 ID：`GAP-P4-01-PROD-SCALE`（见 `OPEN_ITEMS_MASTER.md`）。

## Wave B Steps

### B1 多 worker 启动与 compose 副本 — [x] BAAS_WORKERS→threads；`docker-compose.baas.scale.yml`；Deploy `-Nodes`/`-Workers`/`-WithRedis`
### B2 Redis 限流钩子 — [x] `rate_limit.check_rate_limit` Redis INCR；`capacity.redis_*`
### B3 Postgres 连接池 — [x] `db_postgres` ThreadedConnectionPool（`BAAS_PG_POOL`）
### B4 压测 smoke 证据 — [x] `p4_01_baas_load_smoke.py` + FULL-E2E

## Wave C Steps

### C1 `baas_realms` 表 + realm CRUD — [x]
### C2 Bootstrap/选服列表带 realm — [x] bootstrap + `GET /realms` + `POST /realms/enter` + guest 绑区
### C3 滚服（新开区）+ 合服 job — [x]
### C4 节点注册 heartbeat（与 realm 解耦） — [x]

## 全量业务 E2E

- [x] `p4_01_full_business_e2e.py` → `GAP-P4-01-FULL-E2E`（创建/锁定/导航/GM/health/区服/合服/节点/public）

## 测试与门禁

- `py -3 -m py_compile` 变更 Python
- `node --check` 变更 JS
- `pytest portals/common/core/tests/test_shell_nav.py portals/common/core/tests/test_baas_*.py -q`（相关）
- Wave A：一键脚本 dry-run 或本地 health

## 证据目录

`docs/evidence/2026-11-09/` 或当日目录下 `GAP-P4-01-*.json`
