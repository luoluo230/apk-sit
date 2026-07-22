# Client Bootstrap Contract

This document aligns with `commercial_startup_sequence_gate.py` and `bundle_service.build_client_bootstrap_snapshot`.

## Entry point

- **Primary:** `GET /api/public/runtime-bootstrap`
- **Deprecated:** `GET /api/runtime/version-resolve` (merges `bundle.client` when active bundle exists; response includes `deprecated` and `prefer_runtime_bootstrap`)

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
  "bootstrap": { }
}
```

## Required `bootstrap` fields (gate T2–T3)

| Field | Type | Gate rule |
|-------|------|-----------|
| `resource_relative_path` | string | Must use lowercase `android` segment, not `Android` |
| `catalog_file_name` | string | Non-empty when bundle published |
| `min_client_version` | string | Semver-like label |
| `max_client_version` | string | Semver-like label |
| `rollout_percentage` | int | 0–100 |
| `force_update` | bool | Required key; CI may require `true` when `REQUIRE_FORCE_UPDATE=1` |
| `is_revoked` | bool | Required key |

## Optional but recommended client fields

- `catalog_url`, `config_manifest_url`, `code_manifest_url`
- `apk_url` (Android)
- `resource_server_url`
- `version_code`, `platform`

## Network profile (top-level on bootstrap response when available)

- `network_profile.gateway_ws` must include port `:15050` in CI fixture environments.

## Version-resolve compatibility

When scope has an active published bundle:

1. `version-resolve` merges non-empty fields from `bundle.client`.
2. Response `data.source` is `bundle` (otherwise `version_row`).
3. Meta includes `prefer_runtime_bootstrap: /api/public/runtime-bootstrap`.

## Editor / maclient notes

- Non-Editor builds must not silently override bootstrap network settings from local `ProtocolNetworkSettings`.
- Development Editor may use local overrides; production clients must honor published bundle only.

## Verification chain (Web)

1. `bootstrap_gate_e2e.py` — bootstrap field presence
2. `commercial_startup_sequence_gate.py` — full T2–T3 web sequence
3. Release order verify — HTTP HEAD smoke on catalog/config/code URLs (`order_publish_flow.run_bootstrap_smoke_for_order`)

## Related APIs

- `GET /api/public/release-config` — scope preview + `prefer_runtime_bootstrap`
- `GET /api/release/scopes/<scope_id>?platform=android` — scope + active bundle metadata
