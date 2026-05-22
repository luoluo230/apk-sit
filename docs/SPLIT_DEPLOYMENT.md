# Split Deployment Guide

This project can be deployed as three fully independent deliverables:

- `admin-backend`: developer/admin backend
- `forum-backend`: player forum backend
- `player-static`: static player website for OSS + CDN

## 1) Build Three Independent Folders

```powershell
python scripts/build_split_deploy_bundles.py --out release_bundles
```

Output:

- `release_bundles/admin-backend`
- `release_bundles/forum-backend`
- `release_bundles/player-static`

Each folder can be copied and deployed independently.

## 2) Admin Backend (One-click bootstrap + start)

```bat
cd release_bundles\admin-backend
start_admin.bat
```

Features in one command:

1. Detect Python runtime
2. Auto install Python via `winget` if missing (default enabled)
3. Create local `.venv`
4. Install `requirements.txt` + `requirements-prod.txt`
5. Start service via Waitress

Optional:

```bat
start_admin.bat -CheckOnly
start_admin.bat -Port 5003
start_admin.bat -InstallPythonIfMissing:$false
```

## 3) Forum Backend (One-click bootstrap + start)

```bat
cd release_bundles\forum-backend
start_forum.bat
```

Optional:

```bat
start_forum.bat -CheckOnly
start_forum.bat -Port 5005
start_forum.bat -InstallPythonIfMissing:$false
```

## 4) Player Static Site (One-click check + local serve)

```bat
cd release_bundles\player-static
serve_static.bat
```

Optional:

```bat
serve_static.bat -CheckOnly
serve_static.bat -Port 8080
serve_static.bat -InstallPythonIfMissing:$false
```

For production:

1. Upload all files under `www/` to OSS bucket root
2. Point CDN origin to that bucket
3. Enable compression/cache for:
   - `static/*`
   - `uploaded-media/*`
   - `product-media/*`

## 5) Public URL Configuration (optional but recommended)

Set these on each deployed service to make cross-links accurate:

```dotenv
ADMIN_PUBLIC_URL=https://admin.example.com
PLAYER_PUBLIC_URL=https://www.example.com
FORUM_PUBLIC_URL=https://forum.example.com
```
