# 运维端 × Game-Server 全链路：可执行用例（E2E）

更新时间：2026-06-01

## 用例 1：基础闭环（5 Agent）
1. 启动 5 个 Agent（gateway/auth/game/ops/tcp）并确认黑窗在线。
2. 调 `GET /api/ops-platform/agents?project_id=GomeKu`，确认卡片在线。
3. 调 `POST /api/ops-platform/agents/probe-all`，期望 `fail_count=0`。
4. 在拓扑页绑定 5 个节点到 5 个 Agent。
5. 对每个节点调 `POST /api/ops-platform/topology/node/start-remote`，期望返回 `job_id/trace_id`。
6. 调 `POST /api/ops-platform/runtime/flow-control {op:start}`，期望 `ok=true` 且 run_id 有值。
7. 轮询 `GET /api/ops-platform/runtime/flow-status?run_id=...` 到 success。

判定：全步骤成功 => PASS。

## 用例 2：门禁拦截
1. 将某 Agent 端口改错（或停掉进程）。
2. 执行 probe-all，预期该 Agent FAIL。
3. 尝试 bind-agent/start-remote/flow-control(start)。

判定：应被拦截并返回明确错误码（如 probe required/failed、agent offline、start failed）。

## 用例 3：状态机一致性
1. 触发 start 后检查 job 状态流转：`PENDING -> RUNNING -> SUCCESS/FAILED`。
2. 人工制造超时，检查 `TIMEOUT`。
3. 停止流程，检查 `CANCELED` 或 stop 成功态。

判定：页面显示与后端 `agent/jobs + flow-status` 一致。

## 用例 4：指标一致性
1. 对比 Agent 黑窗与 Web：CPU/MEM/DISK。
2. 对比设备组与卡片（同 device_id）是否一致。
3. 检查业务指标缺失时是否显示“缺失”而非伪值。

判定：控制指标同口径；业务层缺失有显式标识。

## 用例 5：分布式策略
1. 注册多 region/zone Agent。
2. 绑定时按 region/zone 过滤。
3. 目标 region 离线时触发启动。

判定：命中策略正确，失败清单包含 `node_id -> agent_id -> region -> error_code`。
