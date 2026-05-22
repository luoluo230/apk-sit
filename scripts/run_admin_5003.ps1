Set-Location 'F:\apk-site_backup_20260323_070015'
$env:APK_PORT='5003'
$env:APK_HOST='127.0.0.1'
$env:APP_PORTAL_MODE='admin'
& 'F:\apk-site_backup_20260323_070015\venv\Scripts\python.exe' -u -m waitress --listen=127.0.0.1:5003 admin_wsgi:app
