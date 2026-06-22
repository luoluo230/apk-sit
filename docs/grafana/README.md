# Grafana dashboards for apk-site release chain

## Metrics exposed by apk-site

| Metric | Type | Labels | Source |
|--------|------|--------|--------|
| `apk_site_gate_pass_total` | counter | `gate`, `result` (`pass`/`fail`) | `GET /metrics` on admin portal |

Gate scripts increment counters when they pass or fail:

- `portals/common/core/scripts/bootstrap_gate_e2e.py` → `gate="bootstrap_gate_e2e"`
- `portals/common/core/scripts/transport_login_matrix.py` → `gate="transport_login_matrix"`
- `portals/common/core/scripts/commercial_startup_sequence_gate.py` → orchestrates release platform gates
- `portals/common/core/scripts/grafana_smoke_gate.py` → validates `/metrics` scrape shape

## Scrape config (Prometheus)

```yaml
scrape_configs:
  - job_name: apk-site-admin
    metrics_path: /metrics
    static_configs:
      - targets: ['127.0.0.1:5003']
```

## Dashboard

Import `docs/grafana/release-chain-dashboard.json`.

Panels reference:

- `sum(apk_site_gate_pass_total{result="pass"})` — cumulative web gate passes
- `apk_site_gate_pass_total{gate="bootstrap_gate_e2e",result="pass|fail"}` — per-gate breakdown
- `apk_site_cluster_health_passing` — from game-server Ops `/ops/metrics` (when federated via Prometheus)
- `maclient_fps_p50`, `maclient_gateway_rtt_ms` — client telemetry (future scrape from apk-site ingest)

Alert suggestion: fire when `sum(apk_site_gate_pass_total{result="fail"})` increases or federated `apk_site_cluster_health_passing < 9`.

## Local validation

```bash
curl -s http://127.0.0.1:5003/metrics | grep apk_site_gate_pass_total
cd portals/common/core && python scripts/bootstrap_gate_e2e.py
curl -s http://127.0.0.1:5003/metrics | grep bootstrap_gate_e2e
python scripts/grafana_smoke_gate.py
```

Docker dev stack (seeds DB on startup, `APP_PORTAL_MODE=admin`):

```bash
docker compose -f docker-compose.dev.yml up -d --build
curl -s http://127.0.0.1:5003/health
docker compose -f docker-compose.dev.yml down
```

Windows smoke gate (skips cleanly when Docker is unavailable):

```powershell
.\scripts\docker_compose_smoke_gate.ps1
```
