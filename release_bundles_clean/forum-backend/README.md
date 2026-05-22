# forum bundle

This is a fully independent deployment folder.
One command will:
1. check Python runtime
2. auto-install Python via `winget` if missing (optional, default enabled)
3. create `.venv`
4. install runtime dependencies
5. start service

## One-click start (Windows)
```bat
.\start_forum.bat
```

## Check environment only
```bat
.\start_forum.bat -CheckOnly
```

## Custom port
```bat
.\start_forum.bat -Port 5005
```

## Disable auto Python install
```bat
.\start_forum.bat -InstallPythonIfMissing:$false
```

Default port: `5005`  
Portal mode: `forum`
