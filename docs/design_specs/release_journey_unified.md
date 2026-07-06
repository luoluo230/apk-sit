# 发布主路径（Release Journey Unified）

## 唯一入口

**版本代码页 → 行内「开始发布」**

```
GET /admin/projects/{project_id}/release-orders/start?version_id={vc_id}
```

自动 find/create 草稿并跳转编辑页。其它页面不得直接创建空发布单。

## 标准七步

1. 选择 VersionCode（版本代码页）
2. 配置版本组管线（未就绪时阻断，跳转 build-config）
3. 填写发布计划（发布单编辑，深度由环境 form_depth 决定）
4. 触发构建
5. 执行预检
6. 发布（生产环境需审批）
7. 可选验证

## URL 参数契约

| 参数 | 用途 |
|------|------|
| `env_key` | 环境 canonical key |
| `channel_id` | 渠道 ID |
| `platform` | 平台小写 ID |
| `version_id` | **VersionCode 主键**（创建/构建/预检） |
| `release_order_id` | 发布单主键 |
| `version_name` / `version_code` | 只读展示，不作为创建依据 |

Helper：`static/delivery_scope.js` → `DeliveryScope.buildQuery()` / `parseQuery()`

## 页面职责

| 页面 | 角色 |
|------|------|
| 版本代码 | **操作台 / 唯一发布入口** |
| 版本组管线 | 准备步骤（非发布入口） |
| 发布单编辑 | 计划填写 + 下一步 |
| 发布单详情 | 执行态 + 单一下一步 |
| 发布单中心 | 列表管理 |
| 环境详情 | 交付范围准备，不直接发布 |
| 构建产物 | 只读查看 |

## 删除/降级入口

- `/release-orders/new` 无 version_id → 重定向 `/versions?hint=pick_vc`
- 环境详情矩阵「发布」→ 新建 VC / 去版本页
- 发布单列表「新建发布单」→ 去版本页
- 表单：假快捷入口（导入发布计划等）

## Dev/Test vs Prod

| | Dev/Test | Prod |
|---|----------|------|
| form_depth | minimal | full |
| 审批 | 无 | 预检后 awaiting_approval |
| 表单字段 | 目标+原因+负责人 | +验证/回滚/灰度 |
