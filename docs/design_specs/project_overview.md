# 项目总览（Project Overview）

## 路由

- 运行概览：`/admin/projects/{project_id}/overview`
- 渠道管理：`/admin/projects/{project_id}/overview?tab=channels`

## 页内 Tab

| Tab | 内容 |
|-----|------|
| 运行概览 | 渠道 chips（只读）、KPI、环境卡片（可筛选）、最近动态 |
| 渠道管理 | 渠道白名单 CRUD、初始化 Scope、项目环境配置 |

## 环境筛选（运行概览）

Query 参数：`env_key`、`channel_id`、`platform`、`health`

筛选粒度：**环境卡片**（不匹配的环境整卡隐藏）。

## 数据 API

- `GET /api/projects/{id}/overview?env_key=&channel_id=&platform=&health=`
- `GET/POST /api/projects/{id}/environments`
- `PATCH/DELETE /api/projects/{id}/environments/{env_key}`
- 渠道：`POST /api/projects/{id}/channels/{add|remove|disable|enable}`

## 项目环境模型

`projects_db[project_id].release_environments`：

```json
[{"env_key":"development","label":"开发环境","builtin":true,"enabled":true,"order":10}]
```

缺省时种子 4 个内置环境。自定义 `env_key`：`^[a-z][a-z0-9_]{0,31}$`。

## 关键文件

- 模板：`portals/common/core/templates/project_overview.html`
- 脚本：`portals/common/core/static/project_delivery.js`
- 样式：`portals/common/core/static/project_delivery.css`
- 概览聚合：`services/release/release_order_service.py` → `project_overview()`
- 环境注册：`services/release/env_registry.py`
