# Plan Closure — Evidence index (2026-07-29)

Master gate: `py -3 portals/common/core/scripts/run_plan_closure_gate.py --allow-blocked`

iOS GAPs (`GAP-P2-02-E2E-01`, `C-P1-4`) remain **BLOCKED** until `docs/runbooks/ios_provisioning_checklist.md` is fully checked.

## Completed with evidence today

| GAP / W-ID | Evidence |
|------------|----------|
| GAP-P0-02-PRE-01 … PRE-02 | `docs/evidence/2026-07-29/GAP-P0-*.json` |
| GAP-P0-01-CI-01, SEC-02, SEC-01 | secret gate + settings.json |
| GAP-P0-02 Step 2–6 | migrate script, stress gate, multi-worker test |
| GAP-E2E-DEV-01, P1-02, P1-04 | devstack + onboarding spec |
| GAP-P2-01-* | server release e2e + config reload |
| GAP-P2-03-* | staging_incident_notify + grafana |
| GAP-P1-05-OPT-01 | jenkins_sync_node_labels_gate |
| W-P1-2 (partial) | version_group_repo + version_pipeline_resolver |
| C-P1-3 | wechat_minigame_hotupdate.md |

## Still open / partial

| ID | Status | Next action |
|----|--------|-------------|
| GAP-P2-02-E2E-01, C-P1-4 | BLOCKED | macOS + Apple provisioning |
| W-P2-2 | PARTIAL | `project_delivery.js` still >2100 lines — extract `delivery_order_form.js` |
| W-P1-2 | PARTIAL | `version_service.py` facade 1304 lines — extract row/read services |
| C-P1-1, C-P1-2 | PARTIAL | maclient CI gate + legacy path removal |
| GAP-P0-01-DOD-01 | PARTIAL | Create GitHub issues from `github_issues_tracker.md` |

See [`PLAN_CLOSURE_STATUS.md`](PLAN_CLOSURE_STATUS.md) for full symptom → debug map.
