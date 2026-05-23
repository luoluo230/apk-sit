# Windows Cloud Deploy

适用场景：Windows 云服务器。

## 一键部署

在服务器管理员 PowerShell 中执行：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cloud_deploy_windows.ps1
```

带域名并自动 HTTPS 的示例：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cloud_deploy_windows.ps1 `
  -PublicHost apk.example.com `
  -PublicUrl https://apk.example.com `
  -EnableCaddy `
  -InstallPythonIfMissing
```

## 它会做什么

- 自动检查或安装 Python
- 创建 `venv`
- 安装 `requirements.txt` 和 `requirements-prod.txt`
- 更新 `.env`
- 注册开机自启计划任务
- 用 `waitress` 启动 Web 服务
- 可选安装并配置 `Caddy` 做 HTTPS 反向代理
- 自动开放 Windows 防火墙端口

## 需要的条件

- 以管理员身份运行 PowerShell
- 如果启用 HTTPS，域名必须已经解析到这台服务器
- 如果需要自动安装 Python / Caddy，服务器需要能访问 `winget`

## 单独补 HTTPS

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\setup_https_windows.ps1 `
  -AppDir C:\apk-site `
  -PublicHost apk.example.com `
  -AppPort 5003
```

## EIP Deploy

If you want to deploy with a public EIP before binding a domain:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\cloud_deploy_windows.ps1 `
  -PublicEip 1.2.3.4 `
  -InstallPythonIfMissing
```

Priority:
- `PublicUrl` highest
- `PublicHost` for domain deploy
- `PublicEip` for cloud public IP / EIP deploy
