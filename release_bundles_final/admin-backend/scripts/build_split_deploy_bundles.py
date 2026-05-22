#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Build split deployment bundles with one-click bootstrap/start scripts."""

from __future__ import annotations

import argparse
import json
import os
import sqlite3
import stat
import shutil
import subprocess
import sys
import textwrap
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "release_bundles"

COMMON_DIRS = [
    "config",
    "models",
    "routes",
    "services",
    "scripts",
    "templates",
    "static",
    "translations",
    "jenkins-clone-overlay",
    "data",
]

COMMON_FILES = [
    "app_new.py",
    "config.py",
    "utils.py",
    "requirements.txt",
    "requirements-prod.txt",
    ".env.example",
    "admin_wsgi.py",
    "forum_wsgi.py",
    "player_wsgi.py",
]

IGNORE_NAMES = {"__pycache__", "node_modules", "venv", ".venv", ".git", ".DS_Store"}


def _ignore_filter(_src, names):
    ignored = set()
    for name in names:
        if name in IGNORE_NAMES:
            ignored.add(name)
            continue
        if name.startswith("._"):
            ignored.add(name)
            continue
        if name.endswith(".pyc") or name.endswith(".pyo"):
            ignored.add(name)
            continue
    return ignored


def _safe_copy_tree(src: Path, dst: Path):
    if not src.exists():
        return
    if dst.exists():
        _safe_rmtree(dst)
    shutil.copytree(src, dst, ignore=_ignore_filter)


def _safe_copy_file(src: Path, dst: Path):
    if not src.exists():
        return
    dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(src, dst)


def _on_rm_error(func, path, _exc_info):
    os.chmod(path, stat.S_IWRITE)
    func(path)


def _safe_rmtree(path: Path):
    if path.exists():
        shutil.rmtree(path, onerror=_on_rm_error)


def _write_text(path: Path, content: str):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _sanitize_settings_file(path: Path, mode: str, default_port: int):
    if not path.exists():
        return
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return
    except Exception:
        return

    app_cfg = data.setdefault("app", {})
    if isinstance(app_cfg, dict):
        app_cfg["port"] = int(default_port)
        app_cfg["host"] = "0.0.0.0"
        app_cfg["log_dir"] = "logs"
        app_cfg["use_sqlite"] = True
        app_cfg["sqlite_mirror_json"] = False
        app_cfg["sqlite_import_json_on_miss"] = False

    apk_cfg = data.setdefault("apk", {})
    if isinstance(apk_cfg, dict):
        apk_cfg["dir"] = "data/apk"

    jenkins_cfg = data.setdefault("jenkins", {})
    if isinstance(jenkins_cfg, dict):
        jenkins_cfg.setdefault("url", "http://localhost:8080")
        jenkins_cfg.setdefault("port", "8080")
        jenkins_cfg.setdefault("job_name", "Android")
        jenkins_cfg["builds_dir"] = "data/jenkins_instances/default/jobs/Android/builds"
        jenkins_cfg["instances_dir"] = "data/jenkins_instances"
        if not jenkins_cfg.get("war_path"):
            jenkins_cfg["war_path"] = ""

    portal_cfg = data.setdefault("portal", {})
    if isinstance(portal_cfg, dict):
        portal_cfg["mode"] = mode
        portal_cfg["admin_port"] = 5003
        portal_cfg["player_port"] = 5004
        portal_cfg["forum_port"] = 5005
        portal_cfg.setdefault("player_domain", "")
        portal_cfg.setdefault("forum_domain", "")
        portal_cfg.setdefault("admin_domain", "")
        portal_cfg.setdefault("player_public_url", "")
        portal_cfg.setdefault("forum_public_url", "")
        portal_cfg.setdefault("admin_public_url", "")

    path.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _rewrite_env_example(path: Path, mode: str, default_port: int):
    if not path.exists():
        return

    replacements = {
        "APK_DIR": "./data/apk",
        "APK_PORT": str(default_port),
        "APK_HOST": "0.0.0.0",
        "APK_LOG_DIR": "./logs",
        "ADMIN_PORT": "5003",
        "PLAYER_PORT": "5004",
        "FORUM_PORT": "5005",
        "APP_PORTAL_MODE": mode,
        "JENKINS_BUILDS_DIR": "./data/jenkins_instances/default/jobs/Android/builds",
        "JENKINS_INSTANCES_DIR": "./data/jenkins_instances",
        "PLAYER_PUBLIC_URL": "",
        "FORUM_PUBLIC_URL": "",
        "ADMIN_PUBLIC_URL": "",
        "PLAYER_DOMAIN": "",
        "FORUM_DOMAIN": "",
        "ADMIN_DOMAIN": "",
    }

    raw = path.read_text(encoding="utf-8", errors="ignore")
    lines = raw.splitlines()
    output = []
    seen = set()
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            output.append(line)
            continue
        key = stripped.split("=", 1)[0].strip()
        if key in replacements:
            output.append(f"{key}={replacements[key]}")
            seen.add(key)
        else:
            output.append(line)

    for key, value in replacements.items():
        if key not in seen:
            output.append(f"{key}={value}")

    path.write_text("\n".join(output).rstrip() + "\n", encoding="utf-8")


def _sanitize_bundle_data(bundle_dir: Path):
    data_dir = bundle_dir / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Jenkins runtime data should not carry machine-specific historical paths.
    _safe_rmtree(data_dir / "jenkins_instances")
    _safe_rmtree(data_dir / "_legacy_json")
    (data_dir / "jenkins_instances").mkdir(parents=True, exist_ok=True)

    for stale_file in ("jenkins_instances.json", "._jenkins_instances.json"):
        path = data_dir / stale_file
        if path.exists():
            path.unlink()

    db_path = data_dir / "apk_site.db"
    if not db_path.exists():
        return

    now = datetime.now().isoformat()
    conn = sqlite3.connect(str(db_path))
    try:
        cur = conn.cursor()
        cur.execute(
            "UPDATE json_documents SET payload=?, updated_at=? WHERE document_key=?",
            ("[]", now, "data/jenkins_instances.json"),
        )

        cur.execute(
            "SELECT payload FROM json_documents WHERE document_key=?",
            ("data/project_versions.json",),
        )
        row = cur.fetchone()
        if row and row[0]:
            try:
                doc = json.loads(row[0])
            except Exception:
                doc = None
            changed = False
            if isinstance(doc, dict):
                for project_id, versions in doc.items():
                    if not isinstance(versions, list):
                        continue
                    default_output = f"data/apk/{project_id}" if project_id else "data/apk"
                    for version in versions:
                        if not isinstance(version, dict):
                            continue
                        params = version.get("jenkins_params")
                        if isinstance(params, dict):
                            output_dir = params.get("OUTPUT_BASE_DIR")
                            if isinstance(output_dir, str) and (
                                output_dir.startswith("/Users/")
                                or output_dir.startswith("E:\\")
                                or output_dir.startswith("C:\\")
                            ):
                                params["OUTPUT_BASE_DIR"] = default_output
                                changed = True
                if changed:
                    cur.execute(
                        "UPDATE json_documents SET payload=?, updated_at=? WHERE document_key=?",
                        (json.dumps(doc, ensure_ascii=False), now, "data/project_versions.json"),
                    )
        conn.commit()
    finally:
        conn.close()


def _preferred_python_exe() -> str:
    candidates = [
        ROOT / "venv" / "Scripts" / "python.exe",
        ROOT / ".venv" / "Scripts" / "python.exe",
    ]
    for exe in candidates:
        if exe.exists():
            return str(exe)
    return sys.executable


def _runtime_ps1(mode: str, default_port: int, entry: str):
    return textwrap.dedent(
        f"""\
        param(
            [int]$Port={default_port},
            [switch]$CheckOnly,
            [switch]$SkipInstall,
            [bool]$InstallPythonIfMissing=$true
        )

        $ErrorActionPreference = 'Stop'
        Set-Location $PSScriptRoot

        function Write-Step([string]$Text) {{
            Write-Host ""
            Write-Host "[STEP] $Text" -ForegroundColor Cyan
        }}

        function Find-PythonCommand {{
            $python = Get-Command python -ErrorAction SilentlyContinue
            if ($python) {{
                return @{{ Cmd = $python.Source; Args = @() }}
            }}
            $py = Get-Command py -ErrorAction SilentlyContinue
            if ($py) {{
                return @{{ Cmd = $py.Source; Args = @('-3') }}
            }}
            return $null
        }}

        function Refresh-Path {{
            $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
            $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
            $paths = @()
            if ($machinePath) {{ $paths += $machinePath }}
            if ($userPath) {{ $paths += $userPath }}
            if ($paths.Count -gt 0) {{
                $env:Path = ($paths -join ';')
            }}
        }}

        function Install-Python {{
            if (-not $InstallPythonIfMissing) {{
                throw "Python 3.10+ is required. Install Python manually or pass -InstallPythonIfMissing `$true."
            }}
            $winget = Get-Command winget -ErrorAction SilentlyContinue
            if (-not $winget) {{
                throw "Python is missing and winget is unavailable. Install Python 3.10+ manually."
            }}
            Write-Step "Installing Python 3.12 via winget"
            & $winget.Source install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {{
                throw "winget failed to install Python."
            }}
            Refresh-Path
        }}

        function Find-Python {{
            $info = Find-PythonCommand
            if ($info) {{
                return $info
            }}
            Install-Python
            $info = Find-PythonCommand
            if ($info) {{
                return $info
            }}
            throw "Python install completed, but python command still unavailable. Reopen terminal and retry."
        }}

        function Invoke-RootPython([hashtable]$Info, [string[]]$PyArgs) {{
            & $Info.Cmd @($Info.Args) @PyArgs
            if ($LASTEXITCODE -ne 0) {{
                throw "Python command failed: $($PyArgs -join ' ')"
            }}
        }}

        Write-Step "Checking Python"
        $pyInfo = Find-Python
        $versionText = (& $pyInfo.Cmd @($pyInfo.Args) --version 2>&1 | Out-String).Trim()
        if ($LASTEXITCODE -ne 0) {{
            throw "Failed to query Python version"
        }}
        $match = [regex]::Match($versionText, 'Python\\s+(\\d+)\\.(\\d+)\\.(\\d+)')
        if (-not $match.Success) {{
            throw "Invalid Python version output: $versionText"
        }}
        $major = [int]$match.Groups[1].Value
        $minor = [int]$match.Groups[2].Value
        $version = "$($match.Groups[1].Value).$($match.Groups[2].Value).$($match.Groups[3].Value)"
        if ($major -lt 3 -or ($major -eq 3 -and $minor -lt 10)) {{
            throw "Python $version is too old. Required: >= 3.10"
        }}
        Write-Host "[OK] Python version: $version" -ForegroundColor Green

        $venvDir = Join-Path $PSScriptRoot ".venv"
        $venvPy = Join-Path $venvDir "Scripts\\python.exe"
        $needCreateVenv = $false

        if (Test-Path $venvPy) {{
            & $venvPy --version *> $null
            if ($LASTEXITCODE -ne 0) {{
                Write-Host "[WARN] Existing venv is invalid, recreating." -ForegroundColor Yellow
                $needCreateVenv = $true
            }}
        }} else {{
            $needCreateVenv = $true
        }}

        if ($needCreateVenv) {{
            if (Test-Path $venvDir) {{
                Remove-Item -Recurse -Force $venvDir
            }}
            Write-Step "Creating virtual environment"
            Invoke-RootPython -Info $pyInfo -PyArgs @('-m', 'venv', $venvDir)
            Write-Host "[OK] venv created: $venvDir" -ForegroundColor Green
        }} else {{
            Write-Host "[OK] venv exists: $venvDir" -ForegroundColor Green
        }}

        if (-not $SkipInstall) {{
            Write-Step "Installing runtime dependencies"
            & $venvPy -m pip install --upgrade pip setuptools wheel
            if ($LASTEXITCODE -ne 0) {{
                throw "Failed to upgrade pip/setuptools/wheel"
            }}
            $reqMain = Join-Path $PSScriptRoot "requirements.txt"
            if (Test-Path $reqMain) {{
                & $venvPy -m pip install -r $reqMain
                if ($LASTEXITCODE -ne 0) {{
                    throw "Failed to install requirements.txt"
                }}
            }}
            $reqProd = Join-Path $PSScriptRoot "requirements-prod.txt"
            if (Test-Path $reqProd) {{
                & $venvPy -m pip install -r $reqProd
                if ($LASTEXITCODE -ne 0) {{
                    throw "Failed to install requirements-prod.txt"
                }}
            }}
            if (!(Test-Path $reqMain) -and !(Test-Path $reqProd)) {{
                throw "No requirements file found."
            }}
            Write-Host "[OK] dependency install finished" -ForegroundColor Green
        }} else {{
            Write-Host "[INFO] Skip dependency install (-SkipInstall)" -ForegroundColor Yellow
        }}

        Write-Step "Verifying dependencies"
        & $venvPy -c 'import flask, waitress'
        if ($LASTEXITCODE -ne 0) {{
            throw "Dependency verification failed"
        }}

        Write-Step "Preparing runtime directories"
        $bundleData = Join-Path $PSScriptRoot "data"
        $bundleApk = Join-Path $bundleData "apk"
        $bundleJenkins = Join-Path $bundleData "jenkins_instances"
        $bundleLogs = Join-Path $PSScriptRoot "logs"
        foreach ($dir in @($bundleData, $bundleApk, $bundleJenkins, $bundleLogs)) {{
            if (!(Test-Path $dir)) {{
                New-Item -ItemType Directory -Path $dir -Force | Out-Null
            }}
        }}

        if (-not $env:APK_DIR) {{
            $env:APK_DIR = $bundleApk
        }}
        if (-not $env:JENKINS_INSTANCES_DIR) {{
            $env:JENKINS_INSTANCES_DIR = $bundleJenkins
        }}
        if (-not $env:JENKINS_BUILDS_DIR) {{
            $env:JENKINS_BUILDS_DIR = (Join-Path $bundleJenkins "default\\jobs\\Android\\builds")
        }}

        if ($CheckOnly) {{
            Write-Host "[DONE] Environment check passed (CheckOnly)" -ForegroundColor Green
            exit 0
        }}

        $env:APP_PORTAL_MODE = "{mode}"
        $env:APK_PORT = "$Port"

        Write-Step "Starting service"
        Write-Host ("[INFO] mode={mode}, port={{0}}" -f $Port) -ForegroundColor Yellow
        Write-Host ("[INFO] url=http://127.0.0.1:{{0}}" -f $Port) -ForegroundColor Yellow
        & $venvPy -m waitress "--listen=0.0.0.0:$Port" "{entry}"
        """
    )


def _runtime_bat(script_name: str, default_port: int):
    return textwrap.dedent(
        f"""\
        @echo off
        setlocal
        cd /d "%~dp0"
        if "%~1"=="" (
            set "ARGS=-Port {default_port}"
        ) else (
            set "ARGS=%*"
        )
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0\\{script_name}.ps1" %ARGS%
        endlocal
        """
    )


def _runtime_readme(mode: str, default_port: int, script_name: str):
    return textwrap.dedent(
        f"""\
        # {mode} bundle

        This is a fully independent deployment folder.
        One command will:
        1. check Python runtime
        2. auto-install Python via `winget` if missing (optional, default enabled)
        3. create `.venv`
        4. install runtime dependencies
        5. start service

        ## One-click start (Windows)
        ```bat
        .\\{script_name}.bat
        ```

        ## Check environment only
        ```bat
        .\\{script_name}.bat -CheckOnly
        ```

        ## Custom port
        ```bat
        .\\{script_name}.bat -Port {default_port}
        ```

        ## Disable auto Python install
        ```bat
        .\\{script_name}.bat -InstallPythonIfMissing:$false
        ```

        Default port: `{default_port}`  
        Portal mode: `{mode}`
        """
    )


def _build_runtime_bundle(target_dir: Path, mode: str, default_port: int):
    if target_dir.exists():
        _safe_rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    for rel in COMMON_DIRS:
        _safe_copy_tree(ROOT / rel, target_dir / rel)
    for rel in COMMON_FILES:
        _safe_copy_file(ROOT / rel, target_dir / rel)
    _sanitize_settings_file(target_dir / "config" / "settings.json", mode=mode, default_port=default_port)
    _sanitize_settings_file(target_dir / "config" / "settings.example.json", mode=mode, default_port=default_port)
    _rewrite_env_example(target_dir / ".env.example", mode=mode, default_port=default_port)
    _sanitize_bundle_data(target_dir)

    if mode == "admin":
        entry = "admin_wsgi:app"
        script_name = "start_admin"
    elif mode == "forum":
        entry = "forum_wsgi:app"
        script_name = "start_forum"
    else:
        raise ValueError(f"unsupported mode: {mode}")

    _write_text(target_dir / f"{script_name}.ps1", _runtime_ps1(mode=mode, default_port=default_port, entry=entry))
    _write_text(target_dir / f"{script_name}.bat", _runtime_bat(script_name=script_name, default_port=default_port))
    _write_text(target_dir / "README.md", _runtime_readme(mode=mode, default_port=default_port, script_name=script_name))


def _player_static_ps1():
    return textwrap.dedent(
        """\
        param(
            [int]$Port=8080,
            [switch]$CheckOnly,
            [bool]$InstallPythonIfMissing=$true
        )

        $ErrorActionPreference = 'Stop'
        Set-Location $PSScriptRoot

        function Find-PythonCommand {
            $python = Get-Command python -ErrorAction SilentlyContinue
            if ($python) { return @($python.Source, @()) }
            $py = Get-Command py -ErrorAction SilentlyContinue
            if ($py) { return @($py.Source, @('-3')) }
            return $null
        }

        function Refresh-Path {
            $machinePath = [System.Environment]::GetEnvironmentVariable('Path', 'Machine')
            $userPath = [System.Environment]::GetEnvironmentVariable('Path', 'User')
            $paths = @()
            if ($machinePath) { $paths += $machinePath }
            if ($userPath) { $paths += $userPath }
            if ($paths.Count -gt 0) {
                $env:Path = ($paths -join ';')
            }
        }

        function Install-Python {
            if (-not $InstallPythonIfMissing) {
                throw "Python 3.10+ is required. Install Python manually or pass -InstallPythonIfMissing `$true."
            }
            $winget = Get-Command winget -ErrorAction SilentlyContinue
            if (-not $winget) {
                throw "Python is missing and winget is unavailable. Install Python 3.10+ manually."
            }
            Write-Host "[STEP] Installing Python 3.12 via winget" -ForegroundColor Cyan
            & $winget.Source install -e --id Python.Python.3.12 --accept-package-agreements --accept-source-agreements
            if ($LASTEXITCODE -ne 0) {
                throw "winget failed to install Python."
            }
            Refresh-Path
        }

        function Find-Python {
            $info = Find-PythonCommand
            if ($info) { return $info }
            Install-Python
            $info = Find-PythonCommand
            if ($info) { return $info }
            throw "Python install completed, but python command still unavailable. Reopen terminal and retry."
        }

        $www = Join-Path $PSScriptRoot 'www'
        if (!(Test-Path (Join-Path $www 'index.html'))) {
            throw "Missing www/index.html. Rebuild player-static bundle first."
        }

        $pyInfo = Find-Python
        $pyCmd = $pyInfo[0]
        $pyArgs = $pyInfo[1]
        & $pyCmd @pyArgs --version
        if ($LASTEXITCODE -ne 0) {
            throw "Python is not available."
        }

        $ossutil = Get-Command ossutil -ErrorAction SilentlyContinue
        if ($ossutil) {
            Write-Host ("[OK] ossutil detected: {0}" -f $ossutil.Source) -ForegroundColor Green
        } else {
            Write-Host "[INFO] ossutil not found (safe to ignore for local preview)." -ForegroundColor Yellow
        }

        if ($CheckOnly) {
            Write-Host "[DONE] Static bundle environment check passed (CheckOnly)." -ForegroundColor Green
            exit 0
        }

        Write-Host ("[INFO] Serving static site at http://127.0.0.1:{0}" -f $Port) -ForegroundColor Yellow
        & $pyCmd @pyArgs -m http.server $Port --directory $www
        """
    )


def _player_static_bat():
    return textwrap.dedent(
        """\
        @echo off
        setlocal
        cd /d "%~dp0"
        if "%~1"=="" (
            set "ARGS=-Port 8080"
        ) else (
            set "ARGS=%*"
        )
        powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0\\serve_static.ps1" %ARGS%
        endlocal
        """
    )


def _player_static_readme():
    return textwrap.dedent(
        """\
        # player-static bundle

        This is a fully independent static website package in `www/`.
        One command will:
        1. check Python runtime
        2. auto-install Python via `winget` if missing (optional, default enabled)
        3. start static preview service

        ## One-click local preview (Windows)
        ```bat
        .\\serve_static.bat
        ```

        ## Check environment only
        ```bat
        .\\serve_static.bat -CheckOnly
        ```

        ## Custom preview port
        ```bat
        .\\serve_static.bat -Port 8080
        ```

        ## Disable auto Python install
        ```bat
        .\\serve_static.bat -InstallPythonIfMissing:$false
        ```

        ## OSS + CDN deployment
        1. Upload all files under `www/` to OSS bucket root.
        2. Point CDN origin to this bucket.
        3. Enable gzip/brotli and long cache for:
           - `static/*`
           - `uploaded-media/*`
           - `product-media/*`
        """
    )


def _build_player_static_bundle(target_dir: Path, player_base: str, forum_base: str, admin_base: str):
    if target_dir.exists():
        _safe_rmtree(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    www_dir = target_dir / "www"

    cmd = [
        _preferred_python_exe(),
        str(ROOT / "scripts" / "export_player_static.py"),
        "--out",
        str(www_dir),
    ]
    if player_base:
        cmd.extend(["--player-base", player_base])
    if forum_base:
        cmd.extend(["--forum-base", forum_base])
    if admin_base:
        cmd.extend(["--admin-base", admin_base])
    subprocess.run(cmd, check=True, cwd=str(ROOT))

    _write_text(target_dir / "serve_static.ps1", _player_static_ps1())
    _write_text(target_dir / "serve_static.bat", _player_static_bat())
    _write_text(target_dir / "README.md", _player_static_readme())


def main():
    parser = argparse.ArgumentParser(description="Build split deployment bundles")
    parser.add_argument("--out", default=str(DEFAULT_OUT), help="output root directory")
    parser.add_argument("--player-base", default="", help="player public base url")
    parser.add_argument("--forum-base", default="", help="forum public base url")
    parser.add_argument("--admin-base", default="", help="admin public base url")
    args = parser.parse_args()

    out_root = Path(args.out).resolve()
    out_root.mkdir(parents=True, exist_ok=True)

    admin_dir = out_root / "admin-backend"
    forum_dir = out_root / "forum-backend"
    player_dir = out_root / "player-static"

    _build_runtime_bundle(admin_dir, mode="admin", default_port=5003)
    _build_runtime_bundle(forum_dir, mode="forum", default_port=5005)
    _build_player_static_bundle(
        player_dir,
        player_base=args.player_base,
        forum_base=args.forum_base,
        admin_base=args.admin_base,
    )

    print("[DONE] bundles built:")
    print(" -", admin_dir)
    print(" -", forum_dir)
    print(" -", player_dir)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
