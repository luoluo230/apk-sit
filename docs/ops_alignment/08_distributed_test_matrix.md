# 分布式重构全量测试矩阵

更新时间：2026-06-08  
关联方案：分布式拓扑 × Agent × ClusterRelay × 业务测试

## 运行方式

```bash
# PR / 开发循环（无 GameServer 依赖）
pytest tests/ops_distributed -m fast -q

# 本地 / 夜间全量
python tools/run_distributed_acceptance.py --game-server-repo E:/maclient/game-server --base http://127.0.0.1:5003

# game-server 侧
powershell -File E:/maclient/game-server/tools/SmokeTest/DistributedAcceptance.ps1
powershell -File E:/maclient/game-server/tools/Check-Cluster-Health.ps1
```

## 矩阵索引

| 域 | ID 范围 | 自动化位置 |
|----|---------|------------|
| ClusterRelay | CR-01..08 | `DistributedAcceptance.ps1` + live pytest |
| Topology Sync | TS-01..05 | `tests/ops_distributed/unit`, `integration` |
| Agent Jobs | AG-01..08 | `unit`, `integration`, `live` |
| Orchestration | OR-01..07 | `unit`, `live` |
| Business Test | BT-01..12 | `unit`, `integration`, `live` |
| Cross-host / Failure | XR/FM | `integration`, `live` |
| Regression | RG-01..04 | smoke scripts + 本文档 |

## A. ClusterRelay（game-server）

| ID | 层级 | 断言 | 实现 |
|----|------|------|------|
| CR-05 | live | Login 经 Gateway WS 成功 | `live/test_distributed_live.py::test_cr05` |
| CR-06 | live | 全链路 4 步 business plan | `DistributedAcceptance.ps1` |
| CR-08 | live | `--all` dev 回归 | 手动 / `OPS_DEV_UNIFIED_GAMESERVER_ALL=1` |
| RG-03 | script | 15501/15502 探活 | `Check-Cluster-Health.ps1` |

## B. Topology Sync（apk-site）

| ID | 测试文件 | 说明 |
|----|----------|------|
| TS-01..03 | `unit/test_topology_sync.py` | ProbeHost、relay metadata、services 字段 |
| TS-04 | `integration/test_cluster_sync.py` | payload 含 ClusterRelay* |
| XR-01 | `integration/test_cluster_sync.py` | 跨机 ProbeHost |

## C. Agent Jobs

| ID | 测试文件 | 说明 |
|----|----------|------|
| AG-01..03 | `unit/test_agent_jobs.py` | job 归属匹配 |
| AG-04..06 | `integration/test_agent_api.py` | pull/report/幂等 |
| FM-04..05 | `integration/test_agent_api.py` | 并发槽、lease 超时 |
| AG-07..08 | `live/test_distributed_live.py` | agent exec / 四进程 |

## D. Orchestration

| ID | 测试文件 | 说明 |
|----|----------|------|
| OR-01..02 | `unit/test_topology_sync.py` | unified-all 默认关闭 |
| OR-05 | `live/test_distributed_live.py` | tasklist ≥4 进程 |

## E. Business Test

| ID | 测试文件 | 说明 |
|----|----------|------|
| BT-01..04 | `unit/test_gateway_and_preflight.py` | 端点解析、preflight 文案 |
| BT-05..06 | `unit/test_business_steps.py` | PascalCase steps、tasklist 截断 |
| BT-07..08 | `integration/test_business_test_api.py` | API preflight、--ws 传参 |
| BT-09..10 | `live/test_distributed_live.py` | CLI + API 全链路 |
| RG-01 | `integration/test_business_test_api.py` | catalog 路由 |

## F. 故障 / 跨机（部分需 live）

| ID | 状态 | 说明 |
|----|------|------|
| XR-02 | manual | 不可达 ProbeHost → preflight 失败 |
| FM-01..03 | manual | kill auth / 错 token / 仅 gateway |
| FM-02 | manual | cluster Metadata token 不一致 |

## G. 回归

| ID | 实现 |
|----|------|
| RG-02 | `ops_ecosystem_chain.py --distributed` |
| RG-04 | `TEST_SKILL.md` 分布式章节 |

## 一期验收门槛（live）

同机以下全部 PASS：

- OR-05（4 进程）
- CR-05（relay 15501）
- BT-09（CLI auth-login-lifecycle）
- BT-10（API business-test/run）
- AG-07（agent exec status）

## 交叉引用

- 手工 E2E 用例：[`02_e2e_test_cases.md`](02_e2e_test_cases.md)
- 业务测试 schema：[`business_test_plan.schema.json`](business_test_plan.schema.json)
