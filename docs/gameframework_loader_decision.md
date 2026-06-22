# GameFramework Loader Decision — Addressables vs HotUpdate (T-G01 / T-G02)

## Context

maclient ships a hybrid bootstrap: **HybridCLR code hot-update** plus **Addressables resource delivery**, coordinated by the unified release platform (`runtime-bootstrap` → manifest → catalog).

Bundle scope tiers **T0–T7** map to startup-critical assets through optional content packs. The loader must align with `docs/design_specs/unified_release_platform_architecture.md` (when present) and the commercial cold-start sequence exercised by `commercial_startup_sequence_gate.py`.

## Options evaluated

| Dimension | Custom HotUpdate loader | Unity Addressables |
|-----------|-------------------------|-------------------|
| Code delivery | HybridCLR `LoadDll` + signed `code_patch_manifest` | Not applicable for IL2CPP/HybridCLR code |
| Resource delivery | Manual HTTP + local cache paths | Catalog-driven with built-in dependency graph |
| Version resolve | Web `runtime-bootstrap` + `HotUpdateConfig` | Same bootstrap; catalog URL from bootstrap payload |
| Signing / integrity | HMAC manifests (`ConfigPatchManifestSignature`) | Catalog hash + bundle CRC |
| Offline / retry | Custom retry in `StartupHotUpdateBootstrapContext` | Addressables retry + cache APIs |
| Ops surface | apk-site release scopes + topology bindings | Same; catalog path is a release artifact |
| Editor workflow | `verify_split_bundles_runtime.ps1` | Addressables build + catalog export in CI |

## Decision

**Keep the existing split:**

1. **HotUpdate loader (custom)** for **code** and **config patch** domains — HybridCLR DLLs, `code_patch_manifest`, and config sync are not replaceable by Addressables.
2. **Addressables** for **resource** domains (T3–T7 bundles, UI prefabs, audio, localized asset bundles) — catalog + bundle graph is already integrated in the startup path documented in `maclient/docs/framework/热更策略总览.md`.

**Do not** replace the HotUpdate bootstrap with a single Addressables-only loader; that would drop signed code patches and break the commercial gate contract.

## Rationale

- The release platform already publishes separate `code`, `config`, and `resource` targets; Addressables covers only the resource leg.
- `LoadDll` prioritizes manifest-driven code cache (`persistentDataPath/code-cache/`) before catalog fallback — this ordering is required for deterministic cold start.
- Addressables adds value where dependency resolution and incremental content packs matter; duplicating that in a custom loader would increase maintenance without security benefit.

## Implementation guardrails

| Area | Rule |
|------|------|
| Bootstrap | `Version`, `HotUpdateConfig.CurrentClientVersion`, and `PlayerSettings.bundleVersion` must stay aligned (see `Web-Jenkins-Unity-ParameterSpec.md`). |
| Resource URL | Compose from `HotUpdateConfig.ResourceServerUrl` + bootstrap relative paths; **no** legacy `env/platform/major.minor` paths. |
| CI | `verify_split_bundles_runtime.ps1` for split bundles; Addressables catalog build in editor toolchain CI (T-F02–F08). |
| Gate | `commercial_startup_sequence_gate.py` remains the web-side acceptance for bootstrap fields (`active_bundle_id`, `force_update`, `rollout_percentage`). |

## Status

**Accepted** for Wave F — dual-loader model (HotUpdate + Addressables) retained; no migration to Addressables-only loading.
