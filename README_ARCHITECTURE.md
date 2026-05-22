# APK 下载中心 - 架构说明

## 当前结构

- **`app_new.py`**：入口与总逻辑。只负责创建 Flask 应用、注册各 Blueprint、启动时写 base_url、启动下载服务与后台调度。
- **`config.py`**：配置、环境变量、Jenkins 凭证。
- **`utils.py`**：通用工具（load_json、save_json、html_escape、logging）。
- **`models/data.py`**：数据层（用户/项目/统计/事件加载保存、业务辅助函数、登录尝试与审计）。
- **`services/jenkins.py`**：Jenkins API（认证、状态、触发、停止、日志、构建详情）；支持多实例（可选 base_url/builds_dir）。
- **`services/jenkins_manager.py`**：Jenkins 多实例管理（端口检测、启动/停止/删除、环境检查、一键部署脚本）。
- **`services/startup.py`**：启动期服务（下载直链、局域网 IP、飞书告警、定时报表、后台调度）。
- **`routes/auth.py`**：认证（登录、退出、login_required、admin_required）。
- **`routes/home.py`**：首页、/health。
- **`routes/download.py`**：下载、公开下载、二维码、上传、删除。
- **`routes/api.py`**：/api/apks、/api/stats。

## 尚未迁移到 Blueprint 的功能

以下功能目前由占位路由提供（简单跳转或提示），完整逻辑需从原 `app_new.py` 备份恢复后再迁移到独立模块：

- **管理中心**：/admin（面板）、/admin/users、/admin/projects、/admin/audit-log、用户与项目 CRUD。
- **数据分析**：/dashboard、/dashboard/export、/api/analytics/*（趋势、版本、渠道、地域、留存等）。
- **构建管理**：/admin/build、/admin/build/trigger、/build、/api/build/*、/api/jenkins/*。
- **版本与更新说明**：/admin/versions、/admin/changelog/<filename>。
- **Jenkins 管理**：/admin/jenkins、/api/jenkins-manage/*（环境检查、部署日志、端口检测、启动/停止/删除实例、实例列表）。构建页可选择使用哪个 Jenkins 实例，支持多实例并行构建。
- **jenkins-clone 迁入**：将 jenkins-clone 复制到 `apk-site/jenkins-clone/` 后，运行 `python scripts/update_jenkins_paths.py` 可统一路径，便于迁移与直接使用。详见 `docs/JENKINS_MIGRATION.md`。

## 如何恢复并完成迁移

1. **若有原 `app_new.py` 备份**（如 Git 历史、本地副本）：
   - 将其中与 admin、dashboard、build、versions 相关的路由与 HTML/JS 拆到独立文件，例如：
     - `routes/admin.py`：注册 `Blueprint('admin', __name__, url_prefix='/admin')`，实现面板、用户、项目、审计日志。
     - `routes/dashboard.py`：注册 Blueprint，实现 dashboard 页与所有 `/api/analytics/*`、`/dashboard/export`。
     - `routes/build.py`：注册 Blueprint，实现构建页、触发、以及所有 `/api/build/*`、`/api/jenkins/*`。
     - `routes/versions.py`：注册 Blueprint，实现版本管理、changelog、`/build` 页。
   - 在 `app_new.py` 中 `import` 上述 Blueprint 并 `app.register_blueprint(...)`，然后删除或替换 `_register_legacy_routes` / 占位路由。

2. **若没有备份**：
   - 占位路由会保留，/admin、/dashboard、/admin/build 等会跳转或显示“迁移中”。
   - 可按业务需要，在 `routes/` 下新建对应模块，参考现有 `routes/auth.py`、`routes/home.py` 的写法，逐步实现并注册。

## 后期加逻辑建议

- 新功能：在 `routes/` 下新建 `xxx.py`，定义 Blueprint 并实现路由，在 `app_new.py` 中注册即可。
- 新接口：在对应模块（如 `routes/api.py` 或 `routes/dashboard.py`）中新增路由。
- 新后台任务：在 `services/startup.py` 的 `run_background_scheduler` 或新函数中扩展。
