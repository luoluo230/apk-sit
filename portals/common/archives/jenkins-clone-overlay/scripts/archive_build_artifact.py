#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Land build artifact locally + write manifest (apk/ipa/wxgame_bundle)."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path


def _repo_core() -> Path:
    script = Path(__file__).resolve()
    candidates = [
        script.parents[4] / "portals" / "common" / "core",
        Path(os.environ.get("APK_SITE_CORE", "")),
    ]
    for p in candidates:
        if p.is_dir():
            return p
    raise SystemExit(f"找不到 apk-site core: {candidates}")


def main() -> int:
    core = _repo_core()
    if str(core) not in sys.path:
        sys.path.insert(0, str(core))

    artifact_type = os.environ.get("ARTIFACT_TYPE", "apk").strip().lower()
    artifact_file = (
        os.environ.get("ARTIFACT_FILE")
        or os.environ.get("IPA_FILE")
        or os.environ.get("APK_FILE")
        or os.environ.get("WXGAME_BUNDLE")
        or ""
    ).strip()
    if not artifact_file or not Path(artifact_file).is_file():
        print(f"ERROR: artifact missing: {artifact_file}", file=sys.stderr)
        return 1

    from services.build.artifact_landing_service import (  # noqa: WPS433
        build_landing_dir,
        land_file,
        oss_object_key,
        write_landing_manifest,
    )
    from services.build.build_grid import normalize_build_platform

    project_id = os.environ.get("PROJECT_ID", "GomeKu").strip()
    scope_id = os.environ.get("SCOPE_ID", "").strip()
    build_number = os.environ.get("BUILD_NUMBER", "0").strip()
    platform = normalize_build_platform(os.environ.get("RELEASE_PLATFORM", "android"))
    landing = build_landing_dir(project_id, scope_id or "unknown", build_number, platform=platform)
    dest = land_file(artifact_file, landing)
    oss_key = os.environ.get("OSS_ARTIFACT_KEY", "").strip()
    if not oss_key:
        oss_key = oss_object_key(
            project_root=os.environ.get("RELEASE_PROJECT_ROOT", "MyGame1"),
            release_environment=os.environ.get("RELEASE_ENVIRONMENT", "Development"),
            release_channel=os.environ.get("RELEASE_CHANNEL", "common"),
            platform=platform,
            artifact_file_name=Path(dest).name,
        )
    manifest = {
        "ok": True,
        "artifact_type": artifact_type,
        "platform": platform,
        "local_path": dest,
        "oss_key": oss_key,
        "project_id": project_id,
        "scope_id": scope_id,
        "build_number": build_number,
    }
    write_landing_manifest(landing, manifest)
    print(json.dumps(manifest, ensure_ascii=False))

    if artifact_type == "apk":
        try:
            from services.apk_artifact_service import archive_apk, resolve_version_id  # noqa: WPS433

            version_id = os.environ.get("VERSION_ID", "").strip()
            if not version_id:
                version_id = resolve_version_id(
                    project_id,
                    version_code=os.environ.get("VERSION_CODE", ""),
                    version_name=os.environ.get("VERSION_NAME", ""),
                    channel=os.environ.get("VERSION_CHANNEL_ID", os.environ.get("CHANNEL", "")),
                    stage=os.environ.get("VERSION_STAGE", "dev"),
                )
            archive_apk(
                project_id=project_id,
                version_id=version_id,
                apk_path=dest,
                oss_remote_key=oss_key,
            )
        except Exception as exc:
            print(f"WARN: archive_apk fallback: {exc}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
