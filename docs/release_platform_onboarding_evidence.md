# 统一发版平台 Onboarding 验收证据

更新时间：2026-06-09  
规范：[`design_specs/unified_release_platform_architecture.md`](design_specs/unified_release_platform_architecture.md)

## 7 步 Checklist

| 步 | 动作 | GomeKu 状态 | 第二项目状态 |
|----|------|-------------|--------------|
| 1 | 注册 ProjectReleaseManifest | PASS (`data/project_release_manifests.json`) | 待测 |
| 2 | 自动生成 ReleaseScope | PASS (`data/release_scopes.json`) | 待测 |
| 3 | Ops per-env topology + Agent | 运维侧维护 | 待测 |
| 4 | maclient HotUpdateConfig | ProjectId=GomeKu | 待测 |
| 5 | Jenkins commercial plan | 既有流水线 | 待测 |
| 6 | GM Publish + Bundle | **PASS** (`gomeku:development:1001` v1.0.0) | 待测 |
| 7 | bootstrap 验收 | **PASS** (curl + `verify_e2e_release.py` + Unity PlayMode) | 待测 |

## 步 6 — GM Publish + Bundle（Development + 1001，无 Jenkins/APK）

**范围：** `gomeku:development:1001` · `version_name=1.0.0` · `version_code=12`  
**方式：** `portals/common/core/scripts/simulate_e2e_publish.py`（precheck → 审批种子 → `create_bundle_from_publish`，等同 `POST /api/gm-ops/release/publish` 写 bundle 语义）

| 检查项 | 结果 |
|--------|------|
| precheck `topology_runtime_aligned` | true |
| `network_profile_preview.gateway_ws` | `ws://127.0.0.1:15050/ws/` |
| `active_bundle_id` | `rb-20260609-gomeku-development-1001-491226` |
| 版本行 `publish_status` | `published` |

```json
{
  "bundle_id": "rb-20260609-gomeku-development-1001-491226",
  "scope_id": "gomeku:development:1001",
  "version_name": "1.0.0",
  "gateway_ws": "ws://127.0.0.1:15050/ws/",
  "profile_source": "auto",
  "published_by": "e2e-simulate"
}
```

## 步 7 — runtime-bootstrap + 客户端 PlayMode

### 7a. runtime-bootstrap（curl）

```bash
curl "http://127.0.0.1:5003/api/public/runtime-bootstrap?game_id=gomeku-fb64779f94b161d0&game_key=zpf2zNQPoVfiqWjRCSpt70Rx9x4wjTWf&env_key=development&channel=1001&platform=android&version_name=1.0.0"
```

| 字段 | 值 |
|------|-----|
| `ok` | true |
| `scope_id` | `gomeku:development:1001` |
| `active_bundle_id` | `rb-20260609-gomeku-development-1001-491226` |
| `profile_source` | `auto` |
| `network_profile.gateway_ws` | `ws://127.0.0.1:15050/ws/` |
| `bootstrap.resource_relative_path` | `Development/wechat/android/Version_1.0.0/12` |
| `bootstrap.catalog_file_name` | `catalog_1.0.0.bin` |

`python portals/common/core/scripts/verify_e2e_release.py` → **ALL CHECKS PASSED**（2026-06-09）

### 7b. Unity batchmode PlayMode

**入口：** `unity_client_hotupdate_runner.run_unity_client_startup_acceptance`  
**Unity：** `6000.3.15f1` · **报告：** `E:\maclient\Library\ClientAcceptance\client-startup-acceptance-report.json`

```json
{
  "Passed": true,
  "Tier": "entered_login",
  "FinalState": "LoginState",
  "GatewayWs": "ws://127.0.0.1:15050/ws/",
  "CatalogUrl": "https://wlhotupdate1.oss-cn-beijing.aliyuncs.com/MyGame1/Development/wechat/android/Version_1.0.0/12/catalog_1.0.0.bin",
  "UseUnifiedBootstrap": true,
  "ClientVersion": "1.0.0",
  "VersionCode": "12"
}
```

**说明：** PlayMode 在 Editor 下跳过 OSS config/code patch 全量同步（catalog 已由 unified bootstrap 单独验收）；登录仍经真实 Development 拓扑 gateway `:15050`。

### 7c. 多渠道冒烟（只读）

`gomeku:development:1002`：`profile_source=auto`，`gateway_ws` 含 `:15050`，`active_bundle_id` 为空（未发版，符合预期）。

## 验收命令

```bash
curl "http://127.0.0.1:5003/api/release/scopes/gomeku:development:1001"
curl "http://127.0.0.1:5003/api/public/runtime-bootstrap?game_id=gomeku-fb64779f94b161d0&game_key=zpf2zNQPoVfiqWjRCSpt70Rx9x4wjTWf&env_key=development&channel=1001&platform=android&version_name=1.0.0"
python portals/common/core/scripts/release_platform_ci_gate.py --base-url http://127.0.0.1:5003 --scope-id gomeku:development:1001
python portals/common/core/scripts/verify_e2e_release.py
python portals/common/core/scripts/commercial_startup_sequence_gate.py
```

**Unity T4–T7**：`unity_client_hotupdate_runner` 默认 `scenario=smoke`（快速冒烟）；完整热更路径设 `CLIENT_ACCEPTANCE_SCENARIO=basic`。
