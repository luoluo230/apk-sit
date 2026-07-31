# 项目发版控制台

| 项 | 值 |
|---|---|
| 路由 | `/admin/projects/{project_id}/release` |
| BFF API | `GET /api/projects/{pid}/release-console` |
| Batch API | `/api/projects/{pid}/release-batches` |
| 模板 | `project_release_console.html` |
| 主脚本 | `project_release_console.js` |

## 布局 — 三区

| 区域 | ID | 职责 |
|------|-----|------|
| 左 ScopePanel | `#rcScopePanel` | 环境单选；渠道×平台矩阵多选；线上版本/就绪灯 |
| 中 ConfigWorkspace | `#rcConfigWorkspace` | 6 折叠配置区块 |
| 右 ExecutionRail | `#rcExecutionRail` | 就绪清单、唯一主 CTA、批量进度、失败线 |

## 配置区块

1. **发版元信息**（共享）：reason_type、owner、release_window、工单关联、对内说明
2. **发版公告**（共享）：title、body、effective_at、audience；发布时可选同步 GM
3. **客户端配置**（按线 Tab）：version_id 摘要 + 跳转 build-config
4. **服务端配置**（共享）：server_artifact、topology、deploy_server_with_client
5. **发布策略**（共享）：全量/灰度、validation_plan、rollback_plan
6. **执行预览**（只读）：子 ReleaseOrder 摘要、Jenkins 参数预览

## Batch 状态机

`draft` → `building` → `artifacts_ready` → `prechecking` → `ready` → `publishing` → `published` → `verifying` → `completed`

部分失败：`partial_failed`（子 order 明细标红，可重试失败线）

聚合规则：取所有子 order 的「最慢/最差」状态；任一失败且其余成功 → `partial_failed`。

## 权限（环境级 RBAC）

沿用 `release_policy_service` 的 `form_depth` / `require_approval`。生产发布需二次确认 + 变更摘要。

## 迁移

| 旧 URL | 新 URL |
|--------|--------|
| `.../environments/{env}/channels/{ch}/build` | `/release?env=&channel=&platform=&phase=build` |
| `.../environments/{env}/channels/{ch}/release` | `/release?env=&channel=&platform=&phase=publish` |
| `/release-orders/start` | `/release?intent=...` |

Journey 页保留 deprecated banner；侧栏新增「发版」置顶入口。

## UI checklist（11 维）

- [ ] 布局：左 280px / 中 flex / 右 320px；≥1280px 三列同屏
- [ ] 间距：panel padding 16px；区块 gap 12px
- [ ] 字体：继承 pm-shell；标题 18px/600；正文 14px/400
- [ ] 字号层级：h1 发版控制台；h2 区块标题；label 12px
- [ ] 对齐：左栏 label 左对齐；表单 field 纵向 stack
- [ ] 颜色：主 CTA `--pm-accent`；危险 `--pm-danger`；就绪绿/阻塞红
- [ ] 图标：侧栏 nav_release；折叠 chevron；状态灯 dot
- [ ] 响应式：<1024px 右栏折叠为底部 drawer
- [ ] 交互：hover 行高亮；选中线 checkbox；disabled 主 CTA tooltip
- [ ] 空/错/加载：未选环境「请先选择环境」；API 错误 toast；骨架屏
- [ ] 文案：区块标题与 plan 一致；prod 确认弹窗含版本/B bundle diff 摘要

## 验收

- 单项目 `/release` 完成：选 env → 勾选 ≥2 线 → 填配置 → 构建 → 预检 → 发布
- batch 与子 ReleaseOrder 审计可关联
- 旧 URL redirect 无 404
- `release_policy` 与控制台 policy 显示一致
