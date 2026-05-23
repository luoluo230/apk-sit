# 入口与路由注册清单

## 应用装配
- 主装配文件：`app_new.py`
- 仅在 `app_new.py` 中注册 Blueprint。

## 关键 Blueprint 注册（admin 模式）
- `routes/auth.py`：登录/登出
- `routes/admin_routes.py`：后台首页、项目工作台
- `routes/gm_ops.py`：GM 运营中心
- `routes/versions_routes.py`：版本与渠道
- `routes/build_routes.py`：构建相关
- `routes/jenkins_manage_routes.py`：Jenkins 实例管理

## 关键页面路径
- `/admin`
- `/admin/projects/{id}`
- `/admin/gm-ops`
- `/internal/runtime/entrypoint`（运维诊断）

## 约束
- 页面改动先定位路由函数，再修改模板拼接代码。
- 禁止跨目录盲改 `app.py`、`release_bundles*`、`legacy/`。
