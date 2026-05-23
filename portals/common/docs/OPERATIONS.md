# 运维与验收

## 当前生产化能力

1. 核心 JSON 数据自动同步到 SQLite
2. 自动备份 `data/*.json`、`data/*.db` 和业务附件目录
3. 支持从备份 ZIP 恢复 `data/`
4. 内置系统体检脚本与 smoke check
5. 请求带 `X-Request-ID`，并写入 SQLite 请求事件表

## 常用命令

启动服务：

```powershell
F:\apk-site\start.bat
```

迁移 JSON 到 SQLite：

```powershell
C:\python\python.exe F:\apk-site\scripts\migrate_json_to_sqlite.py
```

执行备份：

```powershell
C:\python\python.exe F:\apk-site\scripts\backup_data.py
```

恢复备份：

```powershell
C:\python\python.exe F:\apk-site\scripts\restore_backup.py F:\apk-site\backups\apk-site-YYYYMMDD-HHMMSS.zip
```

系统体检：

```powershell
C:\python\python.exe F:\apk-site\scripts\system_check.py
```

在线 smoke check：

```powershell
C:\python\python.exe F:\apk-site\scripts\smoke_check.py
```

## 平台约定

1. Android 安装包使用 `.apk`
2. iOS 安装包使用 `.ipa`
3. 版本记录必须带 `platform`
4. 页面、统计、下载、上传、版本管理都按平台展示
