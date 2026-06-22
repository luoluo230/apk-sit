# NET8 Gateway Feasibility Spike (T-D14 / T-D15)

## Goal

Evaluate migrating the game-server Gateway WebSocket listener from .NET Framework 4.8 to .NET 8 Kestrel without blocking Wave 3 delivery.

## Scope (spike only)

1. Standalone `GatewayWsPoc` console on `net8.0` using `Microsoft.AspNetCore.App`.
2. Endpoint: `GET /ws/` with echo + heartbeat compatible with maclient `WebSocketTransport`.
3. Compare connection count, TLS termination options, and deploy footprint vs current `WebSocketServerModule`.

## Out of scope

- Full module host migration
- Mongo / EventBus / ClusterRelay port
- Production TLS (see `game-server/docs/tls_configuration.md` + `docs/dev/nginx-wss-dev.conf`)

## Suggested POC layout

```
game-server/tools/GatewayWsPoc/
  GatewayWsPoc.csproj   # net8.0
  Program.cs            # MapGet + WebSocket middleware
  README.md             # run: dotnet run --urls https://127.0.0.1:8443
```

## Acceptance for spike closure

- maclient Editor can connect to POC `wss://127.0.0.1:8443/ws/` with dev cert trust
- Document latency + memory vs Framework gateway on same machine
- Decision recorded in arch-docs `platform-roadmap-wave4.md` §NET8

## Status

Implemented under `game-server/tools/GatewayWsPoc/` (Wave F). See project README for run instructions.
