# Client Bootstrap Contract — Casual BaaS (v1)

Pairs with `packages/client_network/baas` and `casual_baas_server`.

## Entry points

| URL | When |
|-----|------|
| `GET /api/public/client-bootstrap` | **Recommended** — auto-routes by project `server_mode` |
| `GET /api/public/baas-bootstrap` | Direct BaaS bootstrap |

## Query parameters

| Parameter | Required |
|-----------|----------|
| `game_id` | yes |
| `game_key` | yes |
| `env` or `env_key` | yes |
| `service_id` | optional |

## Response (required keys)

```json
{
  "ok": true,
  "framework": "casual_baas",
  "client_module": "baas_client",
  "bootstrap_kind": "baas",
  "project_id": "...",
  "service_id": "uuid",
  "public_api_base": "/api/baas/v1/{service_id}",
  "feature_flags": {},
  "endpoints": { "login": "...", "mail": "..." },
  "auth_header_service": "X-Baas-Service-Id",
  "auth_header_key": "X-Baas-Api-Key"
}
```

Fixture: `portals/common/core/tests/fixtures/baas_bootstrap_contract_v1.sample.json`

## Client startup

1. `BaasNetworkModule.BootstrapAsync(portal, gameId, gameKey, env, apiKey)`
2. `POST {public_api_base}/auth/guest` with `X-Baas-Api-Key`
3. Subsequent calls add player `Authorization` + `X-Baas-Player-Id`

No WebSocket gateway or `network_profile` in BaaS mode.
