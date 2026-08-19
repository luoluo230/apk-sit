# Casual BaaS PVP / Room MVP Boundary

| Item | In scope (MVP) | Out of scope (post-MVP) |
|------|----------------|-------------------------|
| Transport | REST + HTTP long-poll (`wait_ms`) | WebSocket gateway, UDP |
| State | SQLite/Postgres persisted room JSON + replay rows | Sharded room cluster, Redis pub/sub |
| Matchmaking | In-memory public room join | ELO queue, regional shards |
| GM | List/close/kick/finish rooms + replays | Live spectate, frame scrub UI |
| Client | `BaasRoomClient` REST (guest/match/start/push/poll/finish) | Prediction rollback, lockstep |
| Deployment | `PORTAL_SERVER_FRAMEWORKS=baas` on `:5004` | Multi-region active-active |

## Persistence tables

- `baas_rooms(room_id, service_id, status, state_json, updated_at)`
- `baas_room_replays(replay_id, service_id, room_id, battle_id, payload_json, created_at)`

Rooms reload from DB on first access after process restart. Frame waiters remain in-process only.

## Client module pairing

Import **only** `packages/client_network/baas` (or exported zip) for casual server games.  
Do **not** import topology WebSocket module in the same build unless explicitly running dual-stack products.

## Verification

```powershell
py -3 portals/common/core/scripts/run_baas_full_integration_e2e.py
```

Evidence: `docs/evidence/baas-full-integration-latest.json`
