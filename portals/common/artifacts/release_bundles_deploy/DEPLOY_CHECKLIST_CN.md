# 三态独立部署清单

本目录下有三套可独立部署工程：

- `admin-backend`：开发者后台（管理中心、项目、审批、配置、Jenkins）
- `forum-backend`：玩家论坛后端
- `player-static`：玩家官网静态站（OSS + CDN）

## 1. 复制规则

- 部署后台：复制 `admin-backend/` 到服务器
- 部署论坛：复制 `forum-backend/` 到服务器
- 部署玩家官网：上传 `player-static/www/` 到 OSS 根目录并接入 CDN

## 2. admin-backend 启动

在 `admin-backend` 目录执行：

```bat
start_admin.bat -CheckOnly
start_admin.bat
```

可选端口：

```bat
start_admin.bat -Port 5003
```

## 3. forum-backend 启动

在 `forum-backend` 目录执行：

```bat
start_forum.bat -CheckOnly
start_forum.bat
```

可选端口：

```bat
start_forum.bat -Port 5005
```

## 4. player-static 本地预览

在 `player-static` 目录执行：

```bat
serve_static.bat -CheckOnly
serve_static.bat
```

生产部署不需要 Python，直接上传 `www/` 到 OSS 即可。

## 5. 跨域名联动配置（后台管理另外两套）

在 `admin-backend/.env` 配置：

- `ADMIN_PUBLIC_URL=https://admin.yourdomain.com`
- `FORUM_PUBLIC_URL=https://forum.yourdomain.com`
- `PLAYER_PUBLIC_URL=https://www.yourdomain.com`

在 `forum-backend/.env` 也配置同样三项，保证跨系统跳转正确。

## 6. Jenkins（仅开发者后台需要）

`forum-backend` 和 `player-static` 不依赖 Jenkins。  
Jenkins 只在 `admin-backend` 使用（自动打包/构建）。

在 `admin-backend` 目录执行：

```bat
setup_jenkins.bat -CheckOnly
setup_jenkins.bat -StartAfterSetup
```

Docker 模式（可选）：

```bat
setup_jenkins.bat -UseDocker -StartAfterSetup
```

说明：

- 统一构建目录：`./data/apk`
- Jenkins 实例目录：`./data/jenkins_instances`
- Jenkins 构建目录：`./data/jenkins_instances/default/jobs/Android/builds`

## 7. 总体验证（项目根目录执行）

```powershell
& E:\apk-site\scripts\verify_split_bundles_runtime.ps1 -BundlesRoot E:\apk-site\release_bundles_deploy -SkipInstall:$false
```

该脚本会依次执行：

- 三套工程 `CheckOnly`
- 三套工程启动与健康检查
- 三套工程停止校验
