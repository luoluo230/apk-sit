# 统一发版平台 Onboarding 验收证据

更新时间：2026-06-09  
规范：[`design_specs/unified_release_platform_architecture.md`](design_specs/unified_release_platform_architecture.md)

## 7 步 Checklist

| 步 | 动作 | GomeKu 状态 | 第二项目状态 |
|----|------|-------------|--------------|
| 1 | 注册 ProjectReleaseManifest | PASS (`data/project_release_manifests.json`) | 待测 |
| 2 | 自动生成 ReleaseScope | PASS (`data/release_scopes.json`) | 待测 |
| 3 | Ops per-env topology + Agent | 运维侧维护 | 待测 |
| 4 | maclient HotUpdateConfig | ProjectId=GomeKu | 待测 |
| 5 | Jenkins commercial plan | 既有流水线 | 待测 |
| 6 | GM Publish + Bundle | API 已实现 | 待测 |
| 7 | bootstrap 验收 | curl / PlayMode | 待测 |

## 验收命令

```bash
curl "http://127.0.0.1:5003/api/release/scopes/gomeku:production:1001"
curl "http://127.0.0.1:5003/api/public/release-config?project_id=GomeKu&env=prod&channel=1001"
python portals/common/core/scripts/release_platform_ci_gate.py --scope-id gomeku:production:1001
```
