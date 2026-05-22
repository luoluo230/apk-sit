# 排错最短路径（入口问题）

1. 先看端口进程：确认 5003/5004/5005 对应单一 PID。
2. 再看启动命令：必须是 `waitress *_wsgi:app`。
3. 登录后看 `/internal/runtime/entrypoint`：确认入口签名。
4. 再看页面路由：`/admin`、`/admin/projects/{id}`、`/admin/gm-ops`。

常见误区
- 修改了 `app.py` 但线上跑的是 `app_new.py`。
- 浏览器缓存导致“页面没变化”，需强刷并检查 no-store。
