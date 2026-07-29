# Client Bootstrap Contract v2

Contract version: **v2** (P2-02). Shared fixture:

- Web: `portals/common/core/tests/fixtures/runtime_bootstrap_contract_v2.sample.json`
- maclient: `Assets/Editor/Tests/Fixtures/runtime_bootstrap_contract_v2.sample.json`

Validation module: `services/release/bootstrap_contract.py`  
Tests: `tests/e2e/test_bootstrap_contract.py`, `Assets/Editor/Tests/BootstrapContractTests.cs`

## Entry point

- **Primary (production):** `GET /api/public/runtime-bootstrap`
- **Deprecated (compat layer):** `GET /api/runtime/version-resolve` — response headers `Deprecation: true`, `Link: </api/public/runtime-bootstrap>; rel="successor-version"`

Production maclient builds (`DEVELOPMENT` not defined) **must not** silently fall back to OSS `version_metadata.json`.

## Required query parameters (runtime-bootstrap)

| Parameter | Required | Notes |
|-----------|----------|-------|
| `game_id` | yes | Project credential |
| `game_key` | yes | Project credential |
| `env_key` | yes | e.g. `development`, `testing`, `production` |
| `channel` | yes | Channel id or apk subdir |
| `platform` | yes | `android` or `ios` |
| `version_name` | optional | Client-reported version for rollout checks |

## Response shape

```json
{
  "ok": true,
  "project_id": "...",
  "scope_id": "slug:development:channel:android",
  "active_bundle_id": "...",
  "network_profile": { "gateway_ws": "ws://127.0.0.1:15050/ws" },
  "bootstrap": { }
}
```

## Required `bootstrap` fields (v2 gate)

| Field | Type | Gate rule |
|-------|------|-----------|
| `resource_relative_path` | string | Lowercase `android` segment, not `Android` |
| `catalog_file_name` | string | Non-empty when bundle published |
| `min_client_version` | string | Semver-like label |
| `max_client_version` | string | Semver-like label |
| `rollout_percentage` | int | 0–100 |
| `force_update` | bool | Required key |
| `is_revoked` | bool | Required key |

## Required `network_profile` fields (v2)

| Field | Type | Notes |
|-------|------|-------|
| `gateway_ws` | string | CI fixture must include `:15050` |
| `login_http` | string | Recommended |
| `game_ws` | string | Recommended |
| `ops_http` | string | Recommended |

## Config bake single entry (dev / CI)

**唯一写 HotUpdateConfig 的自动化路径：**

1. Jenkins / CI: `HotUpdateConfigSyncCli` (Unity batchmode)
2. 本机 DevStack: `scripts/Sync-DevStackClientConfig.ps1`

手工修改 `HotUpdateConfig.asset` / `ProtocolNetworkSettings.asset` 不应提交；开发请运行 Sync 脚本。

`ProtocolNetworkSettings` dev 默认 `ws://127.0.0.1:15050`；生产网络地址来自 bootstrap `network_profile` inject。

## Client startup order (maclient Main.cs)

1. Unified `runtime-bootstrap` (always in production)
2. `#if DEVELOPMENT` only: optional `version-resolve` retry
3. `#if DEVELOPMENT` only: OSS `version_metadata` when `AllowOssMetadataFallback=true`
4. Failure → explicit error UI (no silent OSS fallback in production)

## Verification chain

1. `tests/e2e/test_bootstrap_contract.py` — fixture contract
2. `bootstrap_gate_e2e.py` — live bootstrap + catalog HEAD + scope API
3. `Assets/Editor/Tests/BootstrapContractTests.cs` — maclient JSON parse gate

## Related APIs

- `GET /api/public/release-config` — scope preview + `prefer_runtime_bootstrap`
- `GET /api/release/scopes/<scope_id>?platform=android` — scope + active bundle metadata
