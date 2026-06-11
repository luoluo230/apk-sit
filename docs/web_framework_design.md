# Web 框架设计

更新时间：2026-06-11  
状态：唯一真源

## 1. 目标

这份文档只回答 Web 自身怎么组织、怎么启动、怎么扩展、怎么避免改乱。

- 运行入口统一
- 路由边界清晰
- 服务层和数据层职责固定
- 发版、运维、项目管理共用同一套装配方式

## 2. 运行入口

唯一应用装配入口：

- `portals/common/core/app_new.py`

运行视图：

- Admin: `admin_wsgi:app`
- Player: `player_wsgi:app`
- Forum: `forum_wsgi:app`

约束：

- 所有 Blueprint 只在 `app_new.py` 注册
- `routes/*` 负责 HTTP 入参、鉴权、返回
- `services/*` 负责业务编排
- `models/*` 负责 JSON 数据读写与领域对象
- `scripts/*` 负责诊断、模拟、验收、部署辅助
- 禁止把业务规则写回 WSGI 入口或模板

## 3. 目录分层

核心目录：

- `portals/common/core/routes`
- `portals/common/core/services`
- `portals/common/core/models`
- `portals/common/core/scripts`
- `portals/common/core/templates`
- `portals/common/core/static`
- `data`

分层职责：

| 层 | 位置 | 职责 |
|---|---|---|
| App | `app_new.py` | Flask 初始化、Blueprint 注册、模式切换、基础中间件 |
| Route | `routes/*` | 页面路由、API 路由、参数归一、权限校验、响应拼装 |
| Service | `services/*` | 发版、运维、Jenkins、项目业务规则 |
| Model | `models/*` | JSON 持久化、记录更新、审计辅助 |
| Script | `scripts/*` | E2E 模拟、CI gate、数据修复、诊断 |
| Data | `data/*` | manifest、scope、bundle、版本、审批、拓扑、agent 等真源 |

## 4. Blueprint 地图

已装配的主模块：

- `auth_bp`：登录、登出、用户资料
- `home_bp`：下载中心、基础站点入口
- `download_bp`：下载、上传、OSS 代理下载
- `api_bp`：健康检查、开放 API、`/api/runtime/version-resolve`
- `workspace_bp`：工作区文件、书签、凭证、便签
- `docs_bp`：站内文档
- `admin_routes_bp`：后台首页、项目中心、审批、审计、设置
- `admin_products_bp`：产品管理
- `build_routes_bp`：构建历史、构建触发、APK 收尾
- `dashboard_routes_bp`：分析看板
- `versions_routes_bp`：版本页
- `jenkins_manage_bp`：Jenkins 实例与环境管理
- `gm_ops_bp`：GM 发版、回滚、公共发版接口
- `gm_legacy_bp`：旧运维/GM 兼容入口
- `commercial_release_bp`：商业发版流水线页面与触发
- `release_bp`：release scope / bundle / manifest 查询与维护

## 5. Web 关键模块边界

### 5.1 项目与版本

- 项目入口：`admin_routes.py`
- 版本管理：`versions_routes.py`
- 构建与 APK 收尾：`build_routes.py`
- Jenkins 管理：`jenkins_manage_routes.py`

### 5.2 发版域

- 运营发版入口：`gm_ops.py`
- 发布域查询入口：`routes/release/scopes.py`
- 领域服务：`services/release/bundle_service.py`

发版域内部真源：

- `data/project_release_manifests.json`
- `data/release_scopes.json`
- `data/release_bundles.json`
- `project_versions` 对应的数据文件

### 5.3 运维域

- 页面入口：`routes/ops/pages.py`
- 拓扑：`routes/ops/topology.py`
- Agent：`routes/ops/agents.py`
- Runtime：`routes/ops/runtime.py`
- Cluster：`routes/ops/cluster.py`
- 服务动作：`routes/ops/services.py`

### 5.4 公共接口域

发版闭环必须经过这些公共接口：

- `GET /api/runtime/version-resolve`
- `GET /api/public/release-config`
- `GET /api/public/runtime-bootstrap`

## 6. 当前采用的数据策略

当前项目仍以 JSON 文件为持久化底座，优点是快，缺点是并发保护弱。

现阶段约束：

- 正式发版逻辑必须走统一 service，不能各模块自己改 JSON
- 版本状态、bundle 状态、scope 上下文必须一次性同步
- 所有 public release API 只能读取 bundle 对齐后的有效状态

## 7. 当前框架成熟度结论

已经成熟的部分：

- Flask 装配结构清楚
- 路由按领域拆分基本成型
- 发版、运维、Jenkins、项目中心已能共存于同一应用
- 关键公共发版接口已统一到 `gm_ops.py + bundle_service.py`

仍需长期治理的部分：

- JSON 持久化后续应迁移到结构化存储或增加更强锁
- `routes` 目录仍存在少量 legacy/bak 文件，需要继续清理
- 运维域与 GM 域仍有一部分历史兼容入口，需要继续收口

## 8. 开发规则

- 新功能先决定属于哪个领域，再决定落在哪个 Blueprint
- 页面改动先定位真实 route，再改模板或前端脚本
- 发布链路相关规则统一放 service，不允许页面层拼业务状态
- 所有对外状态字段优先使用统一主键：
  - `project_id`
  - `env_key`
  - `channel_id`
  - `scope_id`
  - `bundle_id`
  - `topology_id`
  - `runtime_run_id`

## 9. 与发版链路文档的关系

这份文档只管 Web 框架本身。  
Jenkins、Ops、拓扑、Agent、客户端热更、全链路参数和接口统一，全部以 `docs/full_release_chain_architecture.md` 为准。
