# 运维端 × Game-Server 全链路强对齐：接口矩阵（GomeKu）

更新时间：2026-06-01

## 结论标签
- `FULL_MATCH`：页面/接口/Agent 执行能力完整闭环
- `PARTIAL_MATCH`：可通但字段、状态机或语义未完全闭环
- `UI_ONLY`：仅页面或平台逻辑，未触达 game-server 实执行

## A. 主链路（Agent 协议）
| 模块 | 页面入口 | 接口 | Game-Server 能力映射 | 关键字段 | 结论 |
|---|---|---|---|---|---|
| Agent 注册 | Agent 管控 | `POST /api/ops-platform/agent/register` | `OpsPlatformBridge register` | `project_id/device_id/host_name/host_ip/region/zone/rack/port/remote_game_server_port/network.endpoints` | FULL_MATCH |
| Agent 心跳 | Agent 管控 | `POST /api/ops-platform/agent/heartbeat` | `OpsPlatformBridge heartbeat` | `metrics.control.* / metrics.business.* / runtime.*` | PARTIAL_MATCH（business 目前多为 missing） |
| 任务拉取 | 运行/动作 | `POST /api/ops-platform/agent/pull` | `OpsPlatformBridge pull` | `node_id/agent_id/lease/attempt` | FULL_MATCH |
| 任务回执 | 运行/动作 | `POST /api/ops-platform/agent/report` | `OpsPlatformBridge report` + `ExecuteOpsAction` | `RUNNING/SUCCESS/FAILED/TIMEOUT/CANCELED` | FULL_MATCH |

## B. 拓扑与运行闭环
| 模块 | 页面入口 | 接口 | 执行链路 | 结论 |
|---|---|---|---|---|
| 拓扑保存/连线/删边 | 拓扑编排 | `/api/ops-platform/topology/*` | 前端画布 -> 后端拓扑存储 | FULL_MATCH |
| 绑定 Agent | 拓扑编排 | `POST /api/ops-platform/topology/node/bind-agent` | 节点 -> 绑定关系 -> 运行前校验 | FULL_MATCH |
| 远端启动 | 拓扑编排 | `POST /api/ops-platform/topology/node/start-remote` | node -> job enqueue -> agent pull -> action start | FULL_MATCH |
| 全流程运行 | 拓扑编排 | `POST /api/ops-platform/runtime/flow-control` | precheck -> job fanout -> status collect | FULL_MATCH |
| 运行态恢复 | 拓扑编排 | `GET /api/ops-platform/runtime/active` | 刷新后按后端真相恢复 | FULL_MATCH |

## C. 动作/诊断/事件/治理
| 模块 | 核心接口 | 当前映射状态 | 结论 |
|---|---|---|---|
| 动作执行中心 | `/api/ops-platform/actions/validate|approval|execute` | 已能驱动 Agent 任务；动作目录与 game-server 类型动作仍有抽象层 | PARTIAL_MATCH |
| 诊断与体检 | `/api/ops-platform/node-onboarding`, `/api/ops-platform/flow-smoke`, `/api/ops-platform/stress-test` | 可触发测试入口；规则库与节点专属诊断模板未完全按服务类型细化 | PARTIAL_MATCH |
| 事件与追踪 | `/api/ops-platform/events`, `/api/ops-platform/actions/<trace_id>` | 有事件与trace查询；跨模块 trace 关联字段仍需统一规范化 | PARTIAL_MATCH |
| 变更治理 | `/api/ops-platform/change-governance/summary` | 页面与摘要已接；灰度/回滚执行器未形成 game-server 强闭环 | UI_ONLY/PARTIAL |
| 合规审批 | `/api/ops-platform/actions/approval`, 权限校验 | 高危动作后端门禁存在；策略粒度可继续细化到服务动作级 | PARTIAL_MATCH |

## D. Agent 管控（卡片、探测、设备聚合）
| 能力 | 接口 | 状态 |
|---|---|---|
| 列表/分组 | `GET /api/ops-platform/agents`, `GET /api/ops-platform/agents/devices` | FULL_MATCH |
| 单探测/全探测/修复 | `POST /api/ops-platform/agents/probe|probe-all|probe-repair` | FULL_MATCH |
| 过期清理 | `POST /api/ops-platform/agents/cleanup-expired` | FULL_MATCH |
| 2 秒刷新 + 设备聚合 | SSE + polling fallback | FULL_MATCH |
| 双层指标展示（业务优先） | 前端 `ops_platform_agent_control.js` | PARTIAL_MATCH（业务指标缺失时正确标记） |
