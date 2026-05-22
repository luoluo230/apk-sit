# player-static bundle

This is a fully independent static website package in `www/`.
One command will:
1. check Python runtime
2. auto-install Python via `winget` if missing (optional, default enabled)
3. start static preview service

## One-click local preview (Windows)
```bat
.\serve_static.bat
```

## Check environment only
```bat
.\serve_static.bat -CheckOnly
```

## Custom preview port
```bat
.\serve_static.bat -Port 8080
```

## Disable auto Python install
```bat
.\serve_static.bat -InstallPythonIfMissing:$false
```

## OSS + CDN deployment
1. Upload all files under `www/` to OSS bucket root.
2. Point CDN origin to this bucket.
3. Enable gzip/brotli and long cache for:
   - `static/*`
   - `uploaded-media/*`
   - `product-media/*`
