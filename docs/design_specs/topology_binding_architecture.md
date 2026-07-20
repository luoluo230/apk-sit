# 拓扑绑定 — 统一架构规格

> 真源：整合计划「拓扑绑定逻辑梳理」+ P18 环境详情交付线卡片。  
> 运行入口：`/admin/projects/{project_id}/environments/{env_key}` → 平台卡片 → 服务端页签「拓扑」→ 抽屉。

## 一、五层概念（术语分离）

| 层级 | 对象 | 存储 | 用户在抽屉里看到 |
|------|------|------|------------------|
| L1 | 拓扑资产 | JSON registry + contents | 名称、节点/连线数、资产 status |
| L2 | 发布绑定 | SQLite `topology_bindings` | 「已绑定到哪些 scope」 |
| L3 | 节点接线 | JSON node→agent | 不在此抽屉（画布「节点接线」） |
| L4 | 运行实例 | runtime 内存 | 「Runtime 是否运行中」 |
| L5 | Bundle 快照 | release_bundles | 「被哪些 Bundle 引用」（只读提示） |

**禁止**将 L1–L5 混称为「绑定」；UI 文案与 API 字段须标明层级。

## 二、绑定入口与导航收敛

| 入口 | 状态 |
|------|------|
| 环境详情 · 交付线平台卡片 · 服务端 · **拓扑** | **唯一主入口** → 抽屉 |
| 侧栏「拓扑绑定」 | 已移除 |
| 环境详情右栏「拓扑绑定」 | 已移除 |
| `/admin/projects/{id}/topology-bindings` | **兼容深链** → 302 至环境详情 + `open_topology_drawer=1` |
| 拓扑资产页「绑定」 | 深链至环境详情抽屉 |

### 卡片操作分区（scoped：`env_key + channel_id + platform`）

| 区域 | 操作 | 目标 |
|------|------|------|
| **版本**（独立按钮） | 版本 | `/versions` scoped |
| **客户端** 页签 | 构建 / 发版 | channel build/release journey |
| **服务端** 页签 | 拓扑 | 绑定抽屉 |
| | GM | `/actions` scoped |
| | 测试 | `/diagnostics` scoped |

卡片尺寸：`repeat(auto-fill, minmax(260px, 320px))`，max-width 320px。

卡片信息区：拓扑字段显示 **拓扑名称 + 来源 badge**（项目默认 / 环境·渠道·平台 / 大版本）。

## 三、四级绑定模型（L2）

| level | 键 | 说明 |
|-------|-----|------|
| `project_default` | 全空 | 项目兜底 |
| `env_channel_platform` | env + channel + **platform** | 卡片抽屉默认 |
| `env_channel` | env + channel（legacy，platform 空） | 兼容旧数据 |
| `version` | + version_name（可选 platform） | 大版本覆盖 |

**DB**：`topology_bindings.platform TEXT`；唯一索引 `(project_id, env_key, channel_id, platform, version_name)`。

**解析优先级**（有 `version_name` 时）：`version` → `env_channel_platform` → `env_channel` → `project_default` → scope 默认 topology_id。

## 四、单一解析链

全站统一入口：

```python
resolve_topology_binding_for_scope(scope, version_name="")
# → services.release.topology_binding_service.resolve_topology_binding(...)
```

**已接入调用点**：

- 交付线 `_delivery_lines_for_env`（返回 `topology_name`, `binding_source_label`）
- 发布预检 / publish / bundle / release_context / release_policy
- 拓扑绑定抽屉 picker「当前命中」
- 环境运行概览（当 `channel_id + platform` 过滤存在时）

**禁止**并行使用 registry `is_default` 或 scope 裸字段替代 L2 解析（除 fallback_topology_id）。

## 五、拓扑绑定抽屉

### 5.1 布局（自上而下）

1. 标题 + Scope 只读（环境 · 渠道 · 平台）
2. 当前命中：拓扑名 + 来源 badge
3. 筛选：搜索、环境、状态、「优先本环境」
4. 拓扑卡片列表（全量，非下拉）
5. 底部：保存绑定 / 清除覆盖·恢复继承 / 打开拓扑资产

### 5.2 拓扑列表字段

| 字段 | 来源 |
|------|------|
| `topology_id` / `name` | registry |
| `env_key` / `env_label` | registry |
| `status` / `status_label` | registry |
| `is_default` | registry |
| `node_count` / `edge_count` | registry + contents |
| `updated_at` / `owner` | registry |
| `runtime.active` / `run_id` / `reason` | `_runtime_active_for_scope` |
| `binding_refs[]` / `binding_ref_count` | 反查 `topology_bindings` |
| `flags.is_current_hit` | resolve API |
| `flags.is_same_env` | 计算 |
| `flags.selectable` | archived 不可选 |
| `flags.warn_empty_nodes` | node_count ≤ 0 |

**排序**：当前命中 → 同环境 → runtime 活跃 → 已绑定少 → 更新时间。

### 5.3 实现文件

| 层 | 文件 |
|----|------|
| API | `routes/ops/topology.py` |
| 聚合 | `services/release/topology_binding_service.py` → `build_topology_binding_picker()` |
| 抽屉 UI | `static/topology_binding_drawer.js` |
| 样式 | `static/project_environment_detail.css` |
| 模板 | `templates/project_environment_detail.html` |
| 卡片 | `static/project_delivery.js` → `renderDeliveryMatrixHtml()` |

## 六、API 契约

### 6.1 拓扑绑定选择器（主用）

```
GET /api/projects/{project_id}/topology-binding-picker
    ?env_key=&channel_id=&platform=&version_name=
```

**响应 `data`**：

```json
{
  "scope": {
    "project_id": "GomeKu",
    "env_key": "development",
    "channel_id": "wechat",
    "platform": "android",
    "scope_id": "gomeku:development:wechat:android",
    "channel_name": "微信"
  },
  "resolved": {
    "topology_id": "topo-gomeku-dev-main",
    "topology_name": "GomeKu-dev-main",
    "binding_source": "env_channel_platform",
    "binding_source_label": "环境 / 渠道 / 平台",
    "binding_id": "tb-abc123"
  },
  "topologies": [
    {
      "topology_id": "topo-gomeku-dev-main",
      "name": "GomeKu-dev-main",
      "env_key": "development",
      "env_label": "开发",
      "status": "running",
      "status_label": "运行中",
      "is_default": true,
      "node_count": 6,
      "edge_count": 8,
      "updated_at": "2026-07-07T10:00:00",
      "owner": "admin",
      "runtime": { "active": true, "run_id": "run-xyz", "reason": "" },
      "binding_refs": [
        {
          "binding_id": "tb-abc123",
          "level": "env_channel_platform",
          "level_label": "环境 / 渠道 / 平台",
          "env_key": "development",
          "channel_id": "wechat",
          "platform": "android",
          "version_name": "",
          "scope_label": "开发 / 微信 / ANDROID"
        }
      ],
      "binding_ref_count": 1,
      "bundle_ref_count": 0,
      "flags": {
        "is_current_hit": true,
        "is_same_env": true,
        "selectable": true,
        "warn_empty_nodes": false
      }
    }
  ],
  "filters": {
    "environments": [{ "env_key": "development", "label": "开发" }],
    "statuses": [{ "value": "running", "label": "运行中" }]
  }
}
```

### 6.2 保存绑定

```
POST /api/projects/{project_id}/topology-bindings
Content-Type: application/json

{
  "env_key": "development",
  "channel_id": "wechat",
  "platform": "android",
  "topology_id": "topo-gomeku-dev-main"
}
```

默认 level = `env_channel_platform`。高级：`version_name` → level `version`；全空 → `project_default`（需二次确认）。

### 6.3 清除 scope 覆盖

```
DELETE /api/projects/{project_id}/topology-bindings/scope
Content-Type: application/json

{ "env_key": "development", "channel_id": "wechat", "platform": "android" }
```

删除当前 scope 对应 binding 行，恢复继承链 preview。

### 6.4 兼容 API

- `GET/POST /api/projects/{id}/topology-bindings` — 矩阵 CRUD，独立页与 ops 平台仍可用
- `GET /api/ops-platform/topology-bindings/resolve` — 运行平台解析

## 七、发布链路关系

1. 预检失败（拓扑缺失 / runtime 未活跃）→ 深链环境详情 + `open_topology_drawer=1&env_key&channel_id&platform`
2. publish **禁止** silent upsert version 绑定；可选「发布并固化绑定」
3. 交付线卡片拓扑名来自 `_delivery_lines_for_env` 统一解析

## 八、现状对照与 backlog

| 能力 | 目标 | 2026-07-20 状态 |
|------|------|-----------------|
| 绑定入口 | 卡片抽屉 | ✅ 主入口；深链 redirect |
| 拓扑选择 | 全量列表+详情 | ✅ picker API + 抽屉 |
| binding_refs 反查 | 列表内可见 | ✅ |
| Runtime badge | 列表内 | ✅ |
| platform 四级绑定 | DB + resolver | ✅ |
| 解析链 | 单一 | ✅ 交付线/发布/运行概览 |
| 独立绑定页 | redirect | ✅ |
| 预检回链抽屉 | P2 | ✅ JS 深链已改 |
| bundle_ref_count | 可选 | ⏳ 占位 0 |
| 画布「节点接线」改名 | P3 | 待做 |

### 实施优先级（编码阶段）

| 阶段 | 内容 | 状态 |
|------|------|------|
| P0 | platform 列 + picker API + resolver 单测 | ✅ |
| P1 | 卡片 + 抽屉 + 导航收敛 | ✅ |
| P2 | 预检回链 + publish 固化可选 | 部分（回链 ✅） |
| P3 | JSON/SQLite 统一、节点接线改名 | 待做 |

## 九、案例走查：GomeKu · dev · wechat · android

**项目**：`GomeKu`  
**Scope**：`development / wechat / android`  
**Scope ID**：`gomeku:development:wechat:android`

### 步骤 1 — 打开绑定抽屉

1. 访问 `/admin/projects/GomeKu/environments/development`
2. 找到「微信」分组下 **Android** 平台卡片
3. 切换 **服务端** 页签 → 点击 **拓扑**
4. 抽屉 Scope 显示：`开发环境 · 微信 · Android`

或直接深链：  
`/admin/projects/GomeKu/environments/development?open_topology_drawer=1&env_key=development&channel_id=wechat&platform=android`

### 步骤 2 — 选择拓扑

1. 抽屉加载 `GET .../topology-binding-picker?env_key=development&channel_id=wechat&platform=android`
2. 列表顶部应置顶 **当前命中** 拓扑（如 `GomeKu-dev-main`），带 ★ 标记
3. 查看 runtime badge：运行中方可发版
4. 点击目标卡片 → **保存绑定** → `POST .../topology-bindings`

### 步骤 3 — 验证卡片回显

刷新环境详情；Android 卡片拓扑区显示：

- 名称：`GomeKu-dev-main`
- 来源：`环境 / 渠道 / 平台`

### 步骤 4 — 构建与发版

1. **客户端** 页签 → **构建** → channel build journey（1.0.1 dev）
2. 构建完成后 → **发版** → release journey
3. 预检读取同一 resolver 命中拓扑；若 runtime 未活跃，错误链至抽屉深链

### 步骤 5 — 清除覆盖（可选）

抽屉 → **清除覆盖·恢复继承** → `DELETE .../topology-bindings/scope`  
卡片拓扑来源回退至项目默认或 env_channel legacy 链。

### 验收检查点

- [ ] picker 返回 ≥1 拓扑且 `resolved.topology_id` 非空
- [ ] 保存后卡片拓扑名与 picker 选中一致
- [ ] iOS 同环境可绑不同拓扑（platform 维度独立）
- [ ] `/topology-bindings?...` 重定向至环境详情并自动开抽屉
- [ ] 发布单预检「配置拓扑」链至抽屉而非独立页

## 十、缓存与验收

- 静态资源版本：`DELIVERY_ASSET_VER = 20260720-topology-binding-v1`
- 变更文件：`project_delivery.js`, `topology_binding_drawer.js`, `project_environment_detail.css`
- 语法：`node --check` + `python -m py_compile`
- 浏览器：1680 宽屏对比 P18 卡片与抽屉布局（见 `project_environment_detail_p18.md` 验收表）
