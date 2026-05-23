# Remote Deploy For Windows Server

适用场景：你在本地 Windows 机器上，把项目一键发布到 Windows 云服务器。

脚本：
[scripts/deploy_remote_windows.ps1](F:\apk-site\scripts\deploy_remote_windows.ps1)

## 最小用法

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_remote_windows.ps1 `
  -ComputerName 1.2.3.4
```

脚本会提示输入服务器凭据。

## 完整用法

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_remote_windows.ps1 `
  -ComputerName 1.2.3.4 `
  -RemoteAppDir C:\apk-site `
  -PublicHost apk.example.com `
  -PublicUrl https://apk.example.com `
  -EnableCaddy `
  -InstallPythonIfMissing
```

## 它会做什么

1. 本地打包项目
2. 通过 PowerShell Remoting 复制到远程 Windows 服务器
3. 解压到目标目录
4. 调用 `cloud_deploy_windows.ps1`
5. 完成依赖安装、开机自启、可选 HTTPS 配置

## 前提

- 目标服务器已启用 PowerShell Remoting / WinRM
- 你有管理员凭据
- 如果启用 HTTPS，域名已经解析到服务器

## EIP Deploy

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\deploy_remote_windows.ps1 `
  -ComputerName 1.2.3.4 `
  -RemoteAppDir C:\apk-site `
  -PublicEip 1.2.3.4 `
  -InstallPythonIfMissing
```
