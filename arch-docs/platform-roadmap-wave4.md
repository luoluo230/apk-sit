# Wave 4 Platform Roadmap (assessment outlines)

> Wave 4 items are **documented assessments** — implement when product scope requires platformization.

## Docker / containerization (T-B04, T-C16)

| Area | Assessment | Recommendation |
|------|------------|----------------|
| apk-site | Flask + Waitress/Gunicorn + Redis session | Multi-stage Dockerfile: `python:3.11-slim`, non-root user, env-driven portal mode |
| game-server | .NET Framework 4.8 Windows-centric | Prefer Windows Server Core base until NET8 migration; sidecar Mongo/Redis in compose |
| maclient | Unity build agents | Keep CI on bare metal/VM; containerize **tooling** (SmokeTest, InfraValidation) only |
| Networking | Ops ports, WS gateway | Document host port map; use compose profiles for `dev` vs `ci` |

**Exit criteria:** `docker compose up` brings admin portal + game-server smoke stack with documented env file.

## Grafana / observability (T-B05 follow-up)

| Signal | Source today | Grafana panel idea |
|--------|--------------|-------------------|
| Ops `/ops/metrics` | Prometheus text | game-server process counters |
| apk-site audit | JSON logs | approval / release events |
| Cluster health bridge | 9 checks | single stat + heatmap |
| Client performance | `ClientPerformanceReport` | FPS / memory trend |

**Exit criteria:** Import JSON dashboard; alert on cluster health `< 9/9`.

## Editor toolchain (T-F02–F08)

- Protocol codegen dry-run in CI before merge.
- PlayMode acceptance report archived under `Library/ClientAcceptance/`.
- HotUpdate split bundles verified via `verify_split_bundles_runtime.ps1`.

## .NET 8 migration assessment (T-E13–E18, T-D12–D15)

| Component | Blocker | Migration note |
|-----------|---------|----------------|
| HttpListener WebSocket | Platform API | Kestrel + ASP.NET Core WS middleware |
| ClusterRelay | Custom TCP | gRPC or existing relay with `System.IO.Pipelines` |
| Mongo driver | Compatible | Upgrade package on NET8 |
| Unity shared contract | netstandard2.0 | Keep NetworkContract on netstandard2.0 during transition |

**Phases:** (1) extract shared libraries to netstandard2.0, (2) dual-build game-server, (3) cut over gateway host.

## GameFramework loader (T-G01–G02)

- Evaluate Addressables vs custom HotUpdate loader for bundle scope T0–T7.
- Align with unified release platform bootstrap sequence in `docs/design_specs/unified_release_platform_architecture.md`.

## Security / i18n long tail

- TLS/WSS: see `game-server/docs/tls_configuration.md`.
- Client obfuscation + anti-cheat rules: wire `AntiCheatRulesService` violations to Ops events.
- i18n: expand `UILocalizedText` coverage before storefront launch.

---

**Wave 4 gate:** Each row moves from `documented` → `in_progress` only after Wave 3 scaffolding is merged and CI green.
