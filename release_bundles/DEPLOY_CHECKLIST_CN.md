# 三套工程独立部署清单（玩家官网 / 论坛 / 开发后台）

本清单用于确保以下目标：
- 三套工程可单独复制、单独启动、单独部署。
- 玩家官网和论坛可独立域名部署。
- 开发后台可跨服务器维护另外两套（通过项目级域名配置）。

## 1. 需要复制到云端的目录

1. 开发后台：`release_bundles/admin-backend`
2. 玩家论坛：`release_bundles/forum-backend`
3. 玩家官网静态站：`release_bundles/player-static`

说明：
- `player-static` 为纯静态站，可部署到 OSS + CDN。
- `admin-backend` / `forum-backend` 为 Python 服务，启动脚本会自动检查环境并安装依赖。

## 2. 每套工程的一键命令（Windows）

### 2.1 开发后台（admin-backend）

```bat
cd /d admin-backend
start_admin.bat -CheckOnly
start_admin.bat -Port 5003
```

### 2.2 玩家论坛（forum-backend）

```bat
cd /d forum-backend
start_forum.bat -CheckOnly
start_forum.bat -Port 5005
```

### 2.3 玩家官网静态站（player-static）

```bat
cd /d player-static
serve_static.bat -CheckOnly
serve_static.bat -Port 8080
```

## 3. 跨服务器域名配置（重点）

后台会维护玩家官网/论坛链接，建议按“项目级 URL”配置，优先级高于全局配置。

### 3.1 项目级配置（推荐）

进入后台：
- `管理中心 -> 项目管理 -> 编辑项目`

配置以下字段：
- `player_public_url`：玩家官网域名（例如 `https://www.game-a.com`）
- `forum_public_url`：论坛域名（例如 `https://forum.game-a.com`）
- `admin_public_url`：后台域名（例如 `https://ops.game-a.com`）

> 每个项目可配置不同域名，解决多项目隔离部署问题。

### 3.2 全局兜底配置（.env）

在后台服务 `.env` 中可配置全局兜底：

```env
PLAYER_PUBLIC_URL=https://www.default-player.com
FORUM_PUBLIC_URL=https://forum.default-player.com
ADMIN_PUBLIC_URL=https://ops.default-admin.com
```

当项目级 URL 为空时，自动回退到全局配置。

## 4. 反向代理 / CDN 建议

### 4.1 后台与论坛（Python 服务）

- Nginx/Caddy 反代到各自端口。
- 建议启用 HTTPS。
- 保留 `/health` 作为探活地址。

### 4.2 玩家静态站（OSS + CDN）

1. 上传 `player-static/www` 下全部文件到 OSS 桶根目录。
2. CDN 回源指向 OSS 桶。
3. 对 `static/*`、`uploaded-media/*`、`product-media/*` 开启缓存与压缩。

## 5. 部署后验收（最少检查）

### 5.1 开发后台
- `GET /health` 返回 200 且 `{"status":"ok"}`
- `GET /admin` 可访问（未登录时跳登录页）
- 可进入 `项目管理` 并编辑项目级 URL

### 5.2 论坛
- `GET /health` 返回 200
- `GET /forum` 返回 200

### 5.3 玩家官网
- 首页可访问
- 公司简介、新闻、福利、产品详情页可访问
- 产品详情中的论坛/后台入口链接按项目级 URL 生效

## 6. 一键本地验收脚本

根目录提供脚本：

```powershell
powershell -ExecutionPolicy Bypass -File scripts/verify_split_bundles_runtime.ps1
```

该脚本会自动：
- 三套 `CheckOnly`
- 三套拉起服务并探活
- 自动清理端口

