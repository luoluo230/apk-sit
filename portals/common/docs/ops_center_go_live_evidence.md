# 运营中心可上线证据包（自动实测）

- 生成时间: 2026-05-14 09:38:09
- BaseUrl: http://127.0.0.1:5003
- Project: GomeKu
- Env/Channel/Platform: staging/1001/android
- Version: 1.0.0
- 通过率: 11/11

| 验收项 | 结果 | HTTP | 说明 |
|---|---|---:|---|
| 凭据拉取(sync-token) | 通过 | 200 | 已获取 project=GomeKu gameId=demo-game-id |
| 凭据回推(sync-token) | 通过 | 200 | 回推成功 |
| 运行时启动配置(runtime-bootstrap) | 通过 | 200 | 配置拉取成功 publishStatus=rolled_back |
| 发布预检 | 通过 | 200 | 预检通过 |
| 发布审批申请 | 通过 | 200 | 审批单已创建 approvalId=a138f42338de4873 |
| 审批通过并自动执行 | 通过 | 200 | 审批通过并触发执行 |
| 发布后对账 | 通过 | 200 | 对账成功 |
| 发布回滚 | 通过 | 200 | 回滚成功 |
| 闭环证据(closure-evidence/ci) | 通过 | 200 | 已拉取闭环证据 |
| 质量门禁(quality-gate/ci) | 通过 | 200 | 门禁通过 |
| Mongo/Redis 存储观测 | 通过 | 200 | 观测接口可用 |

## 说明
- 如需跑完整审批链路，请提供可用管理员会话 Cookie（`--session-cookie`）。
- Unity 编辑器按钮“从内网拉取/推送到内网”调用的是同一 sync-token 接口，本报告即对应其服务端闭环证据。
