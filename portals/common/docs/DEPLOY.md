# APK 下载中心 - 部署与迁移指南

本文档说明如何在新机器（Windows 或 Mac）上**最少配置、最少命令**完成部署，以及如何**外网可访问**与安全加固。

> **详细部署文档**：设备需求、系统需求、软件环境、Gunicorn、Nginx、HTTPS 完整流程见 [DEPLOYMENT_GUIDE.md](./DEPLOYMENT_GUIDE.md)

---

## 一、快速部署（三步）

### 1. 复制项目

将整个项目目录复制到新机器（或 `git clone`）。

### 2. 配置环境

- 若没有 `.env` 文件：
  - **Mac/Linux**：`cp .env.example .env`
  - **Windows**：`copy .env.example .env`
- 用编辑器打开 `.env`，按需修改（**最少只需改 APK 目录与端口**）：
  - `APK_DIR`：APK 包存放路径（必改）
  - `APK_PORT`：服务端口（默认 5003）
  - 其他如 Jenkins、邮件、飞书等见 `.env.example` 内注释

### 3. 安装依赖并启动

```bash
# 建议使用虚拟环境（可选）
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate

pip install -r requirements.txt
```

- **Mac/Linux**：`./deploy.sh start`（前台）或 `./deploy.sh menu` 选 2 后台、5 开机自启
- **Windows**：双击 `deploy.bat`，选 1 直接启动

启动后控制台会打印：本地地址、局域网地址、外网地址（若已配置）、扫描目录、Jenkins 地址等。

---

## 二、迁移到另一台机器（是否简单？）

**迁移较简单**，步骤少、无数据库：

1. **复制整个项目目录**（含 `data/`、`config/settings.json`、`.env` 若需保留）。
2. 在新机器上按「一、快速部署」操作：创建/编辑 `.env`、安装依赖（`pip install -r requirements.txt`）、运行 `./start.sh` 或 `deploy.sh` / `deploy.bat`。
3. 若需保留数据，请保留：
   - `data/users.json`、`data/projects.json`、`data/project_tasks.json`、`data/documents.json` 等；
   - `data/workspaces/`、`data/doc_attachments/`、`data/product_media/`（用户与产品媒体）；
   - `data/secret.key` 建议保留，否则需用户重新登录。
4. 无需独立数据库，配置集中在 `config/settings.json` 与 `.env`，敏感信息放 `.env` 不提交 Git。

---

## 三、外网可访问与安全加固

### 3.1 配置外网域名

在 `.env` 中配置**公网访问地址**，用于二维码、邮件链接等：

```env
# 推荐：完整 URL（可指定 HTTPS）
PUBLIC_URL=https://apk.yourcompany.com

# 或仅域名（程序会按需补 http/https）
EXTERNAL_DOMAIN=apk.yourcompany.com
```

配置后，启动信息会打印「外网」地址，且 Session Cookie 在 HTTPS 下会设为 Secure。

### 3.2 使用 HTTPS（强烈推荐）

本应用为 HTTP 服务，**外网暴露请务必前置 HTTPS**，由反向代理完成 TLS 终结：

- **Nginx**：配置 `listen 443 ssl`、`ssl_certificate`、`proxy_pass http://127.0.0.1:5003` 等。
- **Caddy**：自动 HTTPS，例如 `apk.yourcompany.com { reverse_proxy 127.0.0.1:5003 }`。

这样：
- 浏览器与代理之间为 HTTPS；
- 代理与本机 Flask 之间可为 HTTP（仅本机访问）。

### 3.3 安全加固项（已实现）

- 响应头：X-Frame-Options、X-Content-Type-Options、X-XSS-Protection、Referrer-Policy 等。
- Session Cookie：HttpOnly、SameSite=Lax；在配置了 HTTPS 的 PUBLIC_URL 时自动 Secure。
- 登录限流：IP 维度限制尝试次数与锁定时长（可在 .env 中配置）。
- 密钥：`APK_SECRET` 或自动生成的 `data/secret.key`，外网部署建议在 .env 中设强随机 `APK_SECRET`。
- 生产环境请设置 `APK_DEBUG=false`。

### 3.4 健康检查

负载均衡或监控可探测：

- `GET /health` 返回 `{"status":"ok","service":"apk-site"}`，用于存活探测。

---

## 四、部署脚本说明

| 脚本 | 用途 |
|------|------|
| `deploy.sh` | Mac/Linux：检查 Python/Flask、无 .env 时从 .env.example 创建、start/stop/restart/autostart |
| `deploy.bat` | Windows：同上菜单式操作 |
| `start.sh` / `start.bat` | 仅启动应用（需已配置 .env） |

应用**只读取 .env**，不再使用 `config.env`；部署脚本会优先从 `.env.example` 生成 `.env`。

---

## 五、常见问题

- **端口被占用**：修改 `.env` 中 `APK_PORT` 后重启。
- **外网访问不到**：确认防火墙/安全组放行对应端口；外网访问建议用 Nginx/Caddy 做 443 反向代理，并配置 `PUBLIC_URL`。
- **登录后刷新掉线**：若用 HTTPS，确保 `.env` 中 `PUBLIC_URL` 为 `https://...`，以便 Session Cookie 正确设为 Secure。
