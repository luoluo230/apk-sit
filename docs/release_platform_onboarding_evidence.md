# 发布平台 Onboarding 证据归档

> 波次 1 验收（T-A08）：记录 gate 与 session 通过的证据链接与摘要。  
> 完整操作见 [arch-docs/release-platform-runbook.md](C:\Users\Administrator\.openclaw\workspace\arch-docs\release-platform-runbook.md)

## 归档目录约定

```
docs/evidence/
  YYYY-MM-DD/
    web-gate.log
    bootstrap-snapshot.json
    session-report.json
    README.md          # 当日验收摘要
```

## 波次 1 验收清单（2026-06-09）

- [x] arch-docs 六文件可串联阅读（README → overall → apk-site → maclient → runbook → TASK-BACKLOG）
- [x] CI 接入 `.github/workflows/release-platform-gate.yml` + `gm_ops_ci_gate.ps1`
- [x] 证据归档 `docs/release_platform_onboarding_evidence.md`
- [x] `simulate_e2e_publish.py` 已落地
- [x] 本机 session 历史 PASS（见上表 2026-06-09）
- [x] 本机 Web gate 实时 PASS（2026-06-21，`seed_release_gate_fixture.py` + `ALL WEB GATES PASSED`）


| 日期 | Web gate | session | scope | bundle | 备注 |
|------|----------|---------|-------|--------|------|
| 2026-06-09 | PASS | PASS | `gomeku:development:1001` | `rb-20260609-gomeku-development-1001-491226` | `tier=entered_game_with_profile`，vc12 |

### Web gate 摘要（2026-06-21 缺口收口）

- 命令：`commercial_startup_sequence_gate.py` + `ops_platform_e2e_gate.py` + `client_telemetry_e2e_gate.py`
- `admin_routes.py`：**557 行**（`admin_routes_size_gate.py` PASS）
- pytest：**12 passed**（含 `test_auth_login_repository`）
- NetworkContract：CI build + `Assets/Plugins/NetworkContract/NetworkContract.dll`
- game-server：InfraValidation（EventBus / IAP / 反作弊 / 断路器集成）

### Web gate 摘要（2026-06-09）
- 结果：`=== ALL WEB GATES PASSED ===`
- `gateway_ws`: `ws://127.0.0.1:15050/ws/`
- `active_bundle_id`: `rb-20260609-gomeku-development-1001-491226`

### session 摘要（2026-06-09）

- 命令：见 runbook §3.3
- 报告：`E:\maclient\Library\ClientAcceptance\client-startup-acceptance-report.json`
- `passed`: true
- `tier`: `entered_game_with_profile`
- `FinalState`: `InGameState`

## CI 接入

- PR 必跑：`.github/workflows/release-platform-gate.yml` → `web-gate` job
- 发版可选：`unity-session` job（`workflow_dispatch` 或 commit 含 `[session-ci]`）

## simulate_e2e_publish（无 APK 路径）

```powershell
cd portals\common\core
py -3 scripts\simulate_e2e_publish.py --help
```

用于热更-only 发版：登记版本、绑定 OSS manifest、执行 publish，不触发 Jenkins APK 构建。详见 `docs/full_release_chain_architecture.md` §5.2。
