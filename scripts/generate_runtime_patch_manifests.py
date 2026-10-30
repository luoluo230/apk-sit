#!/usr/bin/env python3
"""Generate code/config patch manifests from a local Version_* tree for client runtime smoke."""

from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path


def md5_file(path: Path) -> str:
    h = hashlib.md5()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def role_for_code(rel: str) -> str:
    low = rel.replace("\\", "/").lower()
    if "aotmeta" in low:
        return "aotmeta"
    if "hotupdate" in low:
        return "hotupdate"
    if "scriptpatch" in low:
        return "scriptpatch"
    if "symbols" in low:
        return "symbols"
    return "hotupdate"


def build_code_manifest(code_root: Path, *, version: str, version_code: str, base_url: str) -> dict:
    files = []
    for path in sorted(code_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name.endswith(".meta") or path.name.endswith(".json"):
            continue
        rel = path.relative_to(code_root).as_posix()
        files.append(
            {
                "relativePath": rel,
                "remoteObjectKey": f"Development/wechat/android/Version_{version}/{version_code}/code/{rel}",
                "downloadUrl": f"{base_url.rstrip('/')}/code/{rel}",
                "md5": md5_file(path),
                "size": path.stat().st_size,
                "role": role_for_code(rel),
            }
        )
    return {
        "schemaProject": "GomeKu",
        "environment": "Development",
        "channel": "wechat",
        "platform": "Android",
        "clientVersion": version,
        "versionCode": version_code,
        "versionFolder": f"Version_{version}/{version_code}",
        "clientMajor": version.split(".")[0] if version else "1",
        "clientMinor": version.split(".")[1] if version.count(".") >= 1 else "0",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "providerId": "runtime-smoke",
        "baseRemotePrefix": f"Development/wechat/android/Version_{version}/{version_code}/code",
        "files": files,
    }


def build_config_manifest(config_root: Path, *, version: str, version_code: str, base_url: str) -> dict:
    config_root.mkdir(parents=True, exist_ok=True)
    # ensure at least one payload file so config domain has work to do
    marker = config_root / "smoke_config_marker.json"
    if not marker.exists():
        marker.write_text(json.dumps({"ok": True, "source": "runtime-smoke"}, ensure_ascii=False), encoding="utf-8")

    files = []
    for path in sorted(config_root.rglob("*")):
        if not path.is_file():
            continue
        if path.name in {"config_patch_manifest.json", "config_patch_manifest.signature.json"}:
            continue
        if path.name.endswith(".meta"):
            continue
        rel = path.relative_to(config_root).as_posix()
        files.append(
            {
                "relativePath": rel,
                "remoteObjectKey": f"Development/wechat/android/Version_{version}/{version_code}/config/{rel}",
                "downloadUrl": f"{base_url.rstrip('/')}/config/{rel}",
                "md5": md5_file(path),
                "size": path.stat().st_size,
                "sheet": "",
                "category": "smoke",
            }
        )
    return {
        "schemaProject": "GomeKu",
        "environment": "Development",
        "channel": "wechat",
        "platform": "Android",
        "clientVersion": version,
        "versionCode": version_code,
        "versionFolder": f"Version_{version}/{version_code}",
        "clientMajor": version.split(".")[0] if version else "1",
        "clientMinor": version.split(".")[1] if version.count(".") >= 1 else "0",
        "generatedAtUtc": datetime.now(timezone.utc).isoformat(),
        "providerId": "runtime-smoke",
        "baseRemotePrefix": f"Development/wechat/android/Version_{version}/{version_code}/config",
        "files": files,
    }


def write_sig(manifest_path: Path) -> None:
    # Signing disabled in smoke HotUpdateConfig; still place a stub so HEAD exists.
    sig = {
        "manifestFileName": manifest_path.name,
        "algorithm": "none",
        "signature": "",
        "keyId": "smoke",
    }
    manifest_path.with_name(manifest_path.name.replace(".json", ".signature.json")).write_text(
        json.dumps(sig, ensure_ascii=False),
        encoding="utf-8",
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument(
        "--version-root",
        default=r"E:\web\apk-site\portals\common\core\static\Development\wechat\android\Version_1.0.0\21",
    )
    ap.add_argument("--version", default="1.0.0")
    ap.add_argument("--version-code", default="21")
    ap.add_argument(
        "--public-base",
        default="http://127.0.0.1:5003/static/Development/wechat/android/Version_1.0.0/21",
    )
    args = ap.parse_args()
    root = Path(args.version_root)
    code_root = root / "code"
    config_root = root / "config"
    if not code_root.is_dir():
        raise SystemExit(f"missing code dir: {code_root}")

    # Prefer real Jenkins build outputs if static code tree lacks HotUpdate.dll
    src_build = Path(r"E:\maclient\Builds\Development\wechat\android\Version_1.0.0\21\code")
    if src_build.is_dir() and not (code_root / "hotupdate" / "HotUpdate.dll").exists():
        import shutil

        for child in src_build.iterdir():
            dest = code_root / child.name
            if child.is_dir():
                if dest.exists():
                    shutil.rmtree(dest)
                shutil.copytree(child, dest)
            else:
                shutil.copy2(child, dest)

    code_manifest = build_code_manifest(
        code_root, version=args.version, version_code=args.version_code, base_url=args.public_base
    )
    config_manifest = build_config_manifest(
        config_root, version=args.version, version_code=args.version_code, base_url=args.public_base
    )

    code_path = code_root / "code_patch_manifest.json"
    config_path = config_root / "config_patch_manifest.json"
    code_path.write_text(json.dumps(code_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    config_path.write_text(json.dumps(config_manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    write_sig(code_path)
    write_sig(config_path)
    print(
        json.dumps(
            {
                "code_files": len(code_manifest["files"]),
                "config_files": len(config_manifest["files"]),
                "code_manifest": str(code_path),
                "config_manifest": str(config_path),
            },
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
