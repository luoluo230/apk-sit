# Release build failures runbook

## Symptoms

- Release order stuck in `building` then moves to `build_failed`
- Jenkins job `SUCCESS` but release order `build_failed` with `finalize_error`
- OSS upload errors in Unity CLI logs (`[ReleaseUpload][AliyunOSS]`, `ConfigPublish`, `ApkReleaseUploadCli`)
- Artifacts remain `missing` on release order detail

## Quick triage

1. Open Jenkins console for the build number on the release order (`payload.build_job_id`).
2. Check `commercial_android_pipeline.sh` stage markers (`[阶段 N]`).
3. On release order detail, read **客户端健康** panel verify checks and **Bootstrap Gate** recent results.
4. Inspect `release_order_events` for `build_failed` / `build_finalize_failed` payload (`retry_hint`, `failure_summary`).

## Common causes

| Cause | Evidence | Fix |
|-------|----------|-----|
| OSS transient failure | Unity log shows upload start without `done remote=` | Re-trigger build; pipeline retries OSS steps 3× with exponential backoff |
| Unity compile error | Non-zero Unity exit before OSS markers | Fix project/script; rebuild |
| APK archive path wrong | Jenkins SUCCESS + `构建产物登记失败` event | Verify `archive_apk_after_build.py`, `APK_FILE`, Jenkins `JENKINS_HOME/scripts` |
| Missing pipeline step | Precheck reports missing code/resource/config | Complete version build config four steps |
| Wrong scope/platform | Bootstrap gate scope API platform mismatch | Ensure scope id includes platform segment |

## OSS upload retry (pipeline)

`commercial_android_pipeline.sh` wraps OSS-heavy Unity CLI calls with `_run_unity_oss_with_retry`:

- Attempts: 3
- Backoff: 2s → 4s → 8s
- Applies to: ConfigRemotePublish, CommercialReleaseCli (upload mode), ApkReleaseUploadCli

## Web-side recovery

1. Fix root cause (config, OSS credentials, Unity project).
2. From release order detail, use **触发构建** or journey rebuild.
3. After `artifacts_ready`, run precheck → publish → verify.
4. Confirm bootstrap gate PASS in environment runtime **客户端健康** panel.

## CI gates

- `bootstrap_gate_e2e.py` — bootstrap fields + catalog HEAD + scope API platform
- `commercial_startup_sequence_gate.py` — full web T2–T3 chain
- Nightly: `release-platform-gate.yml` schedule runs Unity session job (hard fail)

## Escalation data to collect

- Jenkins build log + `unity_*.log` paths from pipeline
- Release order id, scope_id, platform
- `build_failed` event JSON from timeline
- OSS remote key from pipeline env (`OSS_APK_REMOTE_KEY`)

## Related docs

- [Client bootstrap contract](../client_bootstrap_contract.md)
- [Jenkins local setup](jenkins_local.md)
