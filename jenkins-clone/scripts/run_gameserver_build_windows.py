# -*- coding: utf-8 -*-
"""Windows GameServer-Build: restore, MSBuild, zip, register with Portal."""

from __future__ import annotations

import hashlib
import hmac
import json
import os
import shutil
import subprocess
import sys
import time
import urllib.error
import urllib.request
import zipfile
from pathlib import Path


REPO = Path(os.environ.get("GAMESERVER_ROOT") or r"E:\maclient\game-server")
CSPROJ = REPO / "game-server" / "GameServerApp.csproj"
SLN = REPO / "GameServer.sln"
ENV_FILE = Path(r"E:\web\apk-site\.env")
PORTAL = os.environ.get("APKSITE_BASE_URL", "http://127.0.0.1:5003").rstrip("/")


def _env_file_value(key: str) -> str:
    if not ENV_FILE.is_file():
        return ""
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith(key + "="):
            return line.split("=", 1)[1].strip().strip('"').strip("'")
    return ""


def _run(cmd: list[str], cwd: Path) -> None:
    print("RUN", " ".join(cmd), flush=True)
    proc = subprocess.run(cmd, cwd=str(cwd), check=False)
    if proc.returncode != 0:
        raise SystemExit(f"command failed ({proc.returncode}): {' '.join(cmd)}")


def _msbuild() -> str:
    framework = Path(r"C:\Windows\Microsoft.NET\Framework64\v4.0.30319\MSBuild.exe")
    if framework.is_file():
        return str(framework)
    raise SystemExit("MSBuild.exe not found")


def _nuget() -> str:
    dest = Path(r"C:\Users\Administrator\jenkins\nuget.exe")
    if dest.is_file() and dest.stat().st_size > 100000:
        return str(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    urllib.request.urlretrieve(
        "https://dist.nuget.org/win-x86-commandline/latest/nuget.exe",
        dest,
    )
    return str(dest)


def _build() -> Path:
    if not CSPROJ.is_file():
        raise SystemExit(f"missing project: {CSPROJ}")
    _run([_nuget(), "restore", str(SLN)], REPO)
    out = REPO / "game-server" / "bin" / "Debug"
    _run(
        [
            _msbuild(),
            str(CSPROJ),
            "/p:Configuration=Debug",
            "/p:Platform=AnyCPU",
            "/m",
            "/v:m",
        ],
        REPO / "game-server",
    )
    exe = out / "GameServer.GameServerApp.exe"
    if not exe.is_file():
        raise SystemExit(f"build output missing: {exe}")
    return out


def _zip_output(out_dir: Path) -> Path:
    work = Path(os.environ.get("WORKSPACE") or r"C:\Users\Administrator\jenkins\home\gameserver-work")
    work.mkdir(parents=True, exist_ok=True)
    number = str(os.environ.get("BUILD_NUMBER") or "local")
    dest = work / f"{number}-gameserver.zip"
    if dest.exists():
        dest.unlink()
    with zipfile.ZipFile(dest, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in out_dir.rglob("*"):
            if not path.is_file():
                continue
            if path.suffix.lower() in {".pdb", ".xml"}:
                continue
            zf.write(path, path.relative_to(out_dir).as_posix())
    return dest


def _checksum(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _register(zip_path: Path) -> None:
    secret = _env_file_value("JENKINS_BUILD_WEBHOOK_SECRET")
    if not secret:
        raise SystemExit("JENKINS_BUILD_WEBHOOK_SECRET missing in .env")
    project_id = os.environ.get("PROJECT_ID", "GomeKu").strip() or "GomeKu"
    body = {
        "project_id": project_id,
        "server_release_id": os.environ.get("SERVER_RELEASE_ID", "").strip(),
        "version_label": os.environ.get("SERVER_VERSION_LABEL", "dev").strip() or "dev",
        "protocol_version": "v1",
        "checksum": _checksum(zip_path),
        "source_path": str(zip_path),
        "build_number": os.environ.get("BUILD_NUMBER", ""),
    }
    raw = json.dumps(body, ensure_ascii=False).encode("utf-8")
    sig = hmac.new(secret.encode("utf-8"), raw, hashlib.sha256).hexdigest()
    req = urllib.request.Request(
        f"{PORTAL}/api/internal/jenkins/server-artifact",
        data=raw,
        headers={
            "Content-Type": "application/json",
            "X-Jenkins-Signature": f"sha256={sig}",
        },
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            print(resp.read().decode("utf-8", errors="replace")[:500], flush=True)
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", errors="replace")
        raise SystemExit(f"Portal HTTP {exc.code}: {detail}") from exc


def main() -> int:
    started = time.time()
    out = _build()
    zip_path = _zip_output(out)
    print(f"ZIP {zip_path} bytes={zip_path.stat().st_size}", flush=True)
    _register(zip_path)
    print(f"OK elapsed={int(time.time() - started)}s", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
