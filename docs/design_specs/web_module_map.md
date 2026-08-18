# Web 模块地图

| 域 | 定位 | 入口 | 核心职责 | 不包含 |
|---|---|---|---|---|
| **交付发版** | 客户端版本构建、发布单、跨环境晋级 | `/admin/projects/{id}/release-hub` | 发版中心、发版控制台、版本管理、发布单、构建产物 | 服务器部署、拓扑运维 |
| **项目总览** | 项目状态与环境配置只读视图 | `/admin/projects/{id}/overview` | KPI、活动流、环境/渠道配置 | 发版执行、构建触发 |
| **服务器运行** | 拓扑/BaaS/Agent 运行时 | `/admin/projects/{id}/server-management` | 服务器管理、代理、动作、诊断 | VersionCode、ReleaseOrder |
| **治理与协作** | 审批、审计、任务、文档 | `/admin/approval?project_id={id}` | 审批中心、变更治理、审计、任务、文档 | 发版构建 |
| **项目设置** | 项目元数据与成员 | `/admin/projects/{id}/settings` | 项目设置、环境渠道 | 发版流程 |

## 导航原则

1. **一功能一主入口**：发版执行以「发版中心」为首页，细粒度操作分流到控制台/版本/发布单。
2. **域间不重复**：「服务器管理」只在「服务器运行」域出现；全局侧栏仅保留工作中心/项目列表。
3. **环境上下文**：交付类页面携带 `env_key`；构建历史需 `scoped=1` 防止无范围跳转。
4. **跨环境晋级**：仅在发版中心「跨环境制品晋级」面板操作，生成目标环境 `artifacts_ready` 发布单。

## 评分对齐

| 维度 | 改进项 |
|---|---|
| Dev 操作简单性 (→9) | 发版中心快捷入口 + 一键发版 API |
| Prod 操作简单性 (→8.5+) | 生产发版向导 + 发版控制台批量流程 |
| 单 Scope 灵活性 (→8.5+) | 发版控制台 + 版本管理工作区 |
| 跨环境灵活性 (→8.5+) | artifact-promotions API + 晋级 UI |
| 大厂流程对齐 (→8.5+) | 双级审批 (QA + 发布负责人) + 发布健康度 |
| 后期维护性 (→8.5+) | 本模块地图 + 侧栏四域拆分 |

## 运维路由拆分（维护性）

| 原文件 | 子模块 |
|---|---|
| `routes/ops/topology.py` | `topology_helpers.py`, `topology_project.py`, `topology_platform_catalog.py`, `topology_platform_nodes.py`, `topology_platform_workbench.py`, `topology_platform_structure.py` |
| `routes/ops/agents.py` | `agents_stream.py`, `agents_admin.py`, `agents_protocol.py`, `agents_detail.py` |

`topology.py` / `agents.py` 保留为 facade，仅 import 子模块注册路由。

## E2E 验证

CI 门禁（无需 live server）：

```bash
cd portals/common/core
py -3 scripts/release_hub_e2e_gate.py
# 或
py -3 -m pytest tests/e2e/test_release_hub_e2e.py::ReleaseHubE2ETests -q
```

可选 live server 冒烟（需 admin 在 :5003）：

```bash
set RUN_RELEASE_HUB_LIVE_E2E=1
py -3 -m pytest tests/e2e/test_release_hub_e2e.py::ReleaseHubLiveServerE2ETests -q
```


| API | 用途 |
|---|---|
| `GET /api/projects/{id}/release-hub` | 发版中心 BFF |
| `GET/POST /api/projects/{id}/artifact-promotions` | 跨环境晋级 |
| `GET /api/projects/{id}/release-health` | 发布健康度 |
| `GET /api/projects/{id}/release-console` | 发版控制台 BFF |
| `POST /api/projects/{id}/delivery-attempts/quick-publish` | Dev 一键发版 |
