# admin bundle

This is a fully independent deployment folder.
One command will:
1. check Python runtime
2. auto-install Python via `winget` if missing (optional, default enabled)
3. create `.venv`
4. install runtime dependencies
5. start service

## One-click start (Windows)
```bat
.\start_admin.bat
```

## Check environment only
```bat
.\start_admin.bat -CheckOnly
```

## Custom port
```bat
.\start_admin.bat -Port 5003
```

## Disable auto Python install
```bat
.\start_admin.bat -InstallPythonIfMissing:$false
```

Default port: `5003`  
Portal mode: `admin`
