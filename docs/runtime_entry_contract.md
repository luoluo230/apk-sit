# 运行入口契约（唯一真源）

## 唯一运行入口
- Admin: `waitress admin_wsgi:app`
- Player: `waitress player_wsgi:app`
- Forum: `waitress forum_wsgi:app`

## 代码分层约束
- `app_new.py`?应用组装、中间件、蓝图注册
- `routes/*`?页面/API 路由
- `services/*`?业务服务
- `models/*`?数据模型
- `scripts/*`?部署/启动/诊断

## 禁止事项
- 禁止将 `app.py` 作为运行入口
- 禁止从 `routes/*` 引用临时脚本或归档目录代码

## 运行诊断
登录后访问?`/internal/runtime/entrypoint`
返回字段?`portal_mode`?`entrypoint`?`entry_version`?`apk_port`?`runtime_route_map`?
