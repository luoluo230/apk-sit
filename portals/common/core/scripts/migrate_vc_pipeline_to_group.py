"""VC pipeline → version group migration helper.

Reports differences between each VersionCode's legacy `pipeline` (and bootstrap
scalars) and the version group's `pipeline_template`.

Default: dry-run; only prints diffs grouped by project.

Use `--apply` to copy missing pipelines from VC to the group template (when the
group has none) and propagate the unified template back to all VCs.

Run from the portals/common/core directory:

    py -3 -m scripts.migrate_vc_pipeline_to_group
    py -3 -m scripts.migrate_vc_pipeline_to_group --apply

The script does not delete VC-level pipeline fields; the new resolver will treat
them as a fallback for unmigrated projects.
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any, Dict, List

from repositories.admin import projects_repo, versions_repo
from services.admin import version_service
from services.release.env_registry import normalize_release_env_key


def _project_ids() -> List[str]:
    try:
        rows = projects_repo.list_projects() or {}
    except Exception:
        rows = {}
    if isinstance(rows, dict):
        return sorted(str(k).strip() for k in rows.keys() if str(k or "").strip())
    if isinstance(rows, list):
        return sorted(str((r or {}).get("id") or "").strip() for r in rows if (r or {}).get("id"))
    return []


def _pipeline_diff(template: Dict[str, Any], vc_pipeline: Dict[str, Any]) -> Dict[str, Any]:
    diffs: Dict[str, Any] = {}
    keys = sorted(set(list(template.keys()) + list(vc_pipeline.keys())))
    for key in keys:
        t_val = template.get(key)
        v_val = vc_pipeline.get(key)
        if t_val != v_val:
            diffs[key] = {"template": t_val, "vc": v_val}
    return diffs


def report_project(project_id: str, apply: bool = False) -> None:
    versions = versions_repo.list_versions(project_id) or []
    groups = version_service._load_version_groups_meta(project_id) or []
    if not versions and not groups:
        return
    print(f"\n=== project: {project_id} ===")
    print(f"  groups: {len(groups)}, versions: {len(versions)}")

    by_group: Dict[tuple, Dict[str, Any]] = {}
    for v in versions:
        vn = str(v.get("version_name") or "").strip()
        if not vn:
            continue
        ek = normalize_release_env_key(
            v.get("env_key") or v.get("stage") or "development",
            project_id=project_id,
        )
        pk = str(v.get("platform") or "android").strip().lower()
        key = (vn, ek, pk)
        bucket = by_group.setdefault(key, {"version_codes": []})
        bucket["version_codes"].append(v)

    apply_changes = False
    for (vn, ek, pk), bucket in by_group.items():
        meta = version_service._get_group_meta(project_id, vn, ek, pk) or {}
        template = meta.get("pipeline_template") if isinstance(meta.get("pipeline_template"), dict) else {}
        has_template = bool(template)
        vc_pipelines_with_content = [
            v for v in bucket["version_codes"]
            if isinstance(v.get("pipeline"), dict) and v.get("pipeline")
        ]
        print(f"  - {vn} / {ek or '-'} / {pk}: VCs={len(bucket['version_codes'])} "
              f"template={'yes' if has_template else 'NO'} vc_pipelines={len(vc_pipelines_with_content)}")
        if not has_template and vc_pipelines_with_content:
            # Pick the newest VC pipeline as the template seed.
            best = sorted(
                vc_pipelines_with_content,
                key=lambda r: str(r.get("updated_at") or r.get("created_at") or ""),
                reverse=True,
            )[0]
            seed = best.get("pipeline") or {}
            print(f"    !! group missing pipeline_template — seed from VC {best.get('version_code') or best.get('id')}")
            if apply:
                version_service._save_pipeline_template_to_meta(
                    project_id, vn, ek, pk, "migration_script", seed, {}
                )
                version_service._propagate_pipeline_to_group_scope(
                    versions, project_id, vn, ek, pk, seed, {},
                    str(best.get("updated_at") or "")
                )
                apply_changes = True
        elif has_template:
            for v in vc_pipelines_with_content:
                vc_pipeline = v.get("pipeline") or {}
                diff = _pipeline_diff(template, vc_pipeline)
                if diff:
                    print(f"    diff @ VC {v.get('version_code') or v.get('id')}: {sorted(diff.keys())}")

    if apply and apply_changes:
        versions_repo.save_versions(project_id, versions)
        print(f"  ✔ applied template seed for project {project_id}")


def main() -> int:
    parser = argparse.ArgumentParser(description="Audit VC pipelines vs group templates.")
    parser.add_argument("--apply", action="store_true", help="Write missing templates and propagate.")
    parser.add_argument("--project", type=str, default="", help="Limit to a single project_id.")
    args = parser.parse_args()
    pids = [args.project] if args.project else _project_ids()
    for pid in pids:
        if not pid:
            continue
        try:
            report_project(pid, apply=args.apply)
        except Exception as exc:
            print(f"!! project {pid}: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
