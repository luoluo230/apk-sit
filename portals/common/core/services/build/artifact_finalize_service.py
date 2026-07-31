# -*- coding: utf-8 -*-
"""Finalize Jenkins build artifacts by platform."""

from __future__ import annotations

from services.commercial_release_plan import normalize_release_platform


def finalize_build_artifact_from_jenkins(instance_id: str, build_number: int, *, platform: str = "") -> None:
    plat = normalize_release_platform(platform or "android")
    if plat == "android":
        from services.apk_artifact_service import finalize_apk_from_jenkins_build

        finalize_apk_from_jenkins_build(instance_id, build_number)
        return
    if plat == "ios":
        _finalize_from_landing(instance_id, build_number, artifact_type="ipa")
        return
    if plat == "wechat_minigame":
        _finalize_from_landing(instance_id, build_number, artifact_type="wxgame_bundle")
        return
    from services.apk_artifact_service import finalize_apk_from_jenkins_build

    finalize_apk_from_jenkins_build(instance_id, build_number)


def _finalize_from_landing(instance_id: str, build_number: int, *, artifact_type: str) -> None:
    import os

    from services.build.artifact_landing_service import artifact_landing_root, read_landing_manifest

    root = artifact_landing_root()
    if not os.path.isdir(root):
        raise FileNotFoundError(f"artifact landing root missing: {root}")
    found = None
    for dirpath, _, filenames in os.walk(root):
        if "artifact_manifest.json" not in filenames:
            continue
        manifest = read_landing_manifest(dirpath)
        if str(manifest.get("build_number") or "") != str(build_number):
            continue
        if str(manifest.get("artifact_type") or "") != artifact_type:
            continue
        found = manifest
        break
    if not found:
        raise FileNotFoundError(
            f"landing manifest not found for build={build_number} type={artifact_type}"
        )
