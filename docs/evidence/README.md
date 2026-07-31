# Plan Closure Evidence

> 真源：`docs/architecture/PLAN_CLOSURE_STATUS.md`  
> Master gate：`portals/common/core/scripts/run_plan_closure_gate.py`

## Schema

Each closure item writes one JSON file under `docs/evidence/YYYY-MM-DD/{gap_id}.json`:

```json
{
  "gap_id": "GAP-P0-01-CI-01",
  "status": "DONE",
  "timestamp": "2026-07-29T12:00:00+08:00",
  "command": "py -3 portals/common/core/scripts/production_secret_gate.py",
  "exit_code": 0,
  "artifact_paths": ["docs/evidence/2026-07-29/GAP-P0-01-CI-01.json"],
  "notes": "optional human-readable summary"
}
```

## Rules

1. `status` must be `DONE` for Master gate to pass (unless `BLOCKED` with approved waiver — **none by default**).
2. Mock-only unit tests **do not** produce valid evidence for E2E GAP IDs.
3. iOS E2E (`GAP-P2-02-E2E-01`) remains **BLOCKED** until `ios_provisioning_checklist.md` is fully checked.

## Write evidence from scripts

```python
from scripts.closure_evidence import write_evidence

write_evidence("GAP-P0-01-CI-01", command="...", exit_code=0)
```

## Verify all

```powershell
py -3 portals/common/core/scripts/run_plan_closure_gate.py
```
