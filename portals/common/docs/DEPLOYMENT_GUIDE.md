# APK 下载中心 · 部署与运行完整指南

> 含设备需求、系统需求、软件环境、Gunicorn、Nginx、HTTPS 生产部署全流程

---

## 一、设备需求（硬件）

### 1.1 最低配置（开发/内网试用）

| 项目 | 要求 | 说明 |
|------|------|------|
| CPU | 1 核 | 单机 Flask，无重计算 |
| 内存 | 512 MB | 可运行，建议 1 GB |
| 磁盘 | 2 GB | 不含 APK 存储；系统 + 项目 + 日志 |
| 网络 | 100 Mbps | 内网访问足够 |

适用：开发机、内网小团队试用。

### 1.2 推荐配置（生产/10–50 人）

| 项目 | 要求 | 说明 |
|------|------|------|
| CPU | 2 核 | Gunicorn 多 worker |
| 内存 | 2 GB | 预留日志、缓存、并发 |
| 磁盘 | 20 GB+ | 依 APK 数量；建议 SSD |
| 网络 | 100 Mbps+ | 外网访问、下载加速 |

适用：正式生产、外网访问、多项目协同。

### 1.3 高负载（50–200 人、大文件分发）

| 项目 | 要求 | 说明 |
|------|------|------|
| CPU | 4 核+ | 更多 Gunicorn worker |
| 内存 | 4 GB+ | 并发与文件缓存 |
| 磁盘 | 100 GB+ SSD | APK 量大、备份多 |
| 网络 | 500 Mbps+ | 下载带宽 |

---

## 二、系统需求（操作系统）

### 2.1 支持平台

| 平台 | 版本 | 说明 |
|------|------|------|
| Windows | 10 / 11、Server 2016+ | 使用 `deploy.bat` |
| macOS | 11 (Big Sur)+ | 使用 `deploy.sh` |
| Linux | Ubuntu 20.04+、CentOS 7+、Debian 10+ | 生产首选 |

### 2.2 平台差异

| 项目 | Windows | macOS / Linux |
|------|---------|---------------|
| 启动脚本 | `deploy.bat` | `deploy.sh` |
| 路径分隔 | `\`（代码已用 `os.path.join` 兼容） | `/` |
| 后台进程 | `start /b python app_new.py` | `nohup python3 app_new.py &` |
| 开机自启 | 启动文件夹 `%APPDATA%\...\Startup` | launchd / systemd |

---

## 三、软件环境

### 3.1 数据存储（数据库）

| 存储方式 | 说明 |
|----------|------|
| **JSON 文件** | 默认，用户、项目、任务等存于 `data/*.json`，**无需独立数据库** |
| **SQLite** | 可选，审计日志双写；Python 内置 `sqlite3`，**无需安装**；`.env` 中 `USE_SQLITE=true` 启用 |

**无需安装**：MySQL、PostgreSQL、Redis 等外部数据库。若需启用 SQLite 审计日志，执行 `scripts/migrate_json_to_sqlite.py` 迁移历史数据。

### 3.2 必选

| 软件 | 版本 | 用途 |
|------|------|------|
| Python | 3.8+ | 运行环境 |
| pip | 20.0+ | 依赖安装 |

检查：

```bash
python3 --version   # 或 python --version (Windows)
pip3 --version
```

### 3.3 核心依赖（requirements.txt）

| 包 | 版本 | 说明 |
|----|------|------|
| Flask | 2.3.3 | Web 框架 |
| Flask-WTF | 1.2.1 | CSRF、表单 |
| qrcode[pil] | 7.4.2 | 二维码 |
| Pillow | 10.0.1 | 图片 |
| cryptography | ≥41.0.0 | 加密 |

安装：

```bash
pip install -r requirements.txt
```

### 3.4 生产环境额外依赖

| 包 | 用途 |
|----|------|
| gunicorn | WSGI 生产服务器（替代 Flask 内置） |

安装：

```bash
pip install gunicorn
```

### 3.5 可选（按需）

| 软件 | 用途 |
|------|------|
| Nginx / Caddy | 反向代理、HTTPS、负载均衡 |
| certbot | Let's Encrypt 证书 |
| Redis | 限流/缓存（当前为内存实现，可后续扩展） |

---

## 四、快速部署（开发/内网）

### 4.1 克隆/复制项目

```bash
# 或直接复制项目目录
git clone <repo_url> apk-site && cd apk-site
```

### 4.2 配置环境

```bash
cp .env.example .env
# 编辑 .env，至少修改：
#   APK_DIR   - APK 存放路径
#   APK_PORT  - 端口（默认 5003）
```

### 4.3 安装与启动

```bash
python3 -m venv venv
source venv/bin/activate   # Windows: venv\Scripts\activate
pip install -r requirements.txt

# Mac/Linux
./deploy.sh start          # 前台
./deploy.sh start-bg       # 后台

# Windows
deploy.bat                 # 菜单选 1 启动
```

访问：`http://localhost:5003`，默认管理员 `admin` / `admin123`。

---

## 五、生产部署（Gunicorn + Nginx + HTTPS）

### 5.1 目录与权限

```bash
cd /opt/apk-site   # 或您的部署目录
chown -R www-data:www-data /opt/apk-site   # Linux，按实际用户调整
chmod +x deploy.sh
```

### 5.2 Gunicorn 配置

项目已包含 `gunicorn_config.py`，可按需修改。环境变量可覆盖部分配置：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| GUNICORN_BIND | 127.0.0.1:5003 | 监听地址 |
| GUNICORN_WORKERS | (2×CPU)+1 | Worker 数 |
| GUNICORN_TIMEOUT | 120 | 超时秒数 |
| GUNICORN_LOG_LEVEL | info | 日志级别 |

安装生产依赖：

```bash
pip install -r requirements.txt -r requirements-prod.txt
```

### 5.3 启动 Gunicorn

```bash
# 前台测试
gunicorn -c gunicorn_config.py app_new:app

# 后台运行（示例）
nohup gunicorn -c gunicorn_config.py app_new:app >> logs/gunicorn.log 2>&1 &
echo $! > logs/gunicorn.pid
```

**注意**：Gunicorn 启动前需先加载 `.env`，建议在项目根目录执行；`gunicorn_config.py` 会通过 `chdir` 设置工作目录。

### 5.4 systemd 服务（Linux 推荐）

创建 `/etc/systemd/system/apk-site.service`：

```ini
[Unit]
Description=APK Download Center
After=network.target

[Service]
Type=simple
User=www-data
Group=www-data
WorkingDirectory=/opt/apk-site
Environment="PATH=/opt/apk-site/venv/bin"
ExecStart=/opt/apk-site/venv/bin/gunicorn -c /opt/apk-site/gunicorn_config.py app_new:app
ExecReload=/bin/kill -s HUP $MAINPID
Restart=on-failure
RestartSec=5

[Install]
WantedBy=multi-user.target
```

启用：

```bash
sudo systemctl daemon-reload
sudo systemctl enable apk-site
sudo systemctl start apk-site
sudo systemctl status apk-site
```

---

## 六、Nginx 反向代理

### 6.1 安装 Nginx

**Ubuntu/Debian:**

```bash
sudo apt update
sudo apt install nginx -y
```

**CentOS/RHEL:**

```bash
sudo yum install nginx -y
# 或
sudo dnf install nginx -y
```

### 6.2 基础 HTTP 配置

创建 `/etc/nginx/sites-available/apk-site`（Ubuntu）或 `/etc/nginx/conf.d/apk-site.conf`（CentOS）：

```nginx
server {
    listen 80;
    server_name apk.yourcompany.com;   # 替换为您的域名或 IP

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_set_header X-Request-ID $request_id;
        proxy_connect_timeout 60s;
        proxy_send_timeout 120s;
        proxy_read_timeout 120s;
    }

    # 健康检查
    location /health {
        proxy_pass http://127.0.0.1:5003/health;
        access_log off;
    }
}
```

启用并测试：

```bash
# Ubuntu
sudo ln -s /etc/nginx/sites-available/apk-site /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl reload nginx
```

### 6.3 HTTPS 配置（Let's Encrypt）

安装 certbot：

```bash
# Ubuntu
sudo apt install certbot python3-certbot-nginx -y

# CentOS
sudo yum install certbot python3-certbot-nginx -y
```

申请证书（确保域名已解析到本机 80 端口）：

```bash
sudo certbot --nginx -d apk.yourcompany.com
```

certbot 会自动修改 Nginx 配置并启用 HTTPS。若需手动配置：

```nginx
server {
    listen 443 ssl http2;
    server_name apk.yourcompany.com;

    ssl_certificate /etc/letsencrypt/live/apk.yourcompany.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/apk.yourcompany.com/privkey.pem;
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_prefer_server_ciphers on;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256:ECDHE-ECDSA-AES256-GCM-SHA384:ECDHE-RSA-AES256-GCM-SHA384;

    client_max_body_size 100M;

    location / {
        proxy_pass http://127.0.0.1:5003;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto https;
        proxy_set_header X-Request-ID $request_id;
    }
}
```

### 6.4 可选：HTTP 自动跳转 HTTPS

```nginx
server {
    listen 80;
    server_name apk.yourcompany.com;
    return 301 https://$server_name$request_uri;
}
```

### 6.5 .env 与 PUBLIC_URL

使用 HTTPS 时，请在 `.env` 中配置：

```env
PUBLIC_URL=https://apk.yourcompany.com
APK_DEBUG=false
```

这样 Session Cookie 会自动加 Secure，二维码等链接也会使用 HTTPS。

---

## 七、Caddy 替代方案（自动 HTTPS）

若使用 Caddy，可不手动申请证书：

```bash
# 安装（示例）
sudo apt install -y debian-keyring debian-archive-keyring apt-transport-https
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/gpg.key' | sudo gpg --dearmor -o /usr/share/keyrings/caddy-stable-archive-keyring.gpg
curl -1sLf 'https://dl.cloudsmith.io/public/caddy/stable/debian.deb.txt' | sudo tee /etc/apt/sources.list.d/caddy-stable.list
sudo apt update && sudo apt install caddy

# 配置 /etc/caddy/Caddyfile
apk.yourcompany.com {
    reverse_proxy 127.0.0.1:5003
}
```

Caddy 会自动申请并续期证书。

---

## 八、防火墙

### 8.1 生产建议

- 仅开放 80/443，不对外暴露 5003。
- 5003 仅本机 Nginx 可访问。

**UFW（Ubuntu）：**

```bash
sudo ufw allow 80/tcp
sudo ufw allow 443/tcp
sudo ufw deny 5003
sudo ufw enable
```

**firewalld（CentOS）：**

```bash
sudo firewall-cmd --permanent --add-service=http
sudo firewall-cmd --permanent --add-service=https
sudo firewall-cmd --reload
```

---

## 九、备份与恢复

### 9.1 手动备份

```bash
python scripts/backup_data.py
# 输出：backups/apk-site-YYYYMMDD-HHMMSS.zip
```

### 9.2 定时备份

应用内置每日定时备份（默认凌晨 2 点），可通过 `.env` 配置：

```env
BACKUP_HOUR=2
BACKUP_RETENTION_COUNT=7
BACKUP_SCHEDULED=true
```

### 9.3 恢复

解压备份到项目目录，覆盖 `data/` 等目录后重启应用。

---

## 十、监控与健康检查

### 10.1 接口

| 路径 | 说明 |
|------|------|
| `GET /health` | 存活探测，负载均衡用 |
| `GET /api/status` | 统计、性能数据 |

### 10.2 Nginx 健康检查示例

```nginx
upstream apk_backend {
    server 127.0.0.1:5003;
    keepalive 32;
}

# 在 location 中使用
proxy_pass http://apk_backend;
```

---

## 十一、部署检查清单

| 序号 | 检查项 |
|------|--------|
| 1 | Python 3.8+、依赖已安装 |
| 2 | `.env` 已配置（APK_DIR、APK_PORT 等） |
| 3 | `APK_DEBUG=false` |
| 4 | 外网部署已配置 `PUBLIC_URL`（HTTPS 地址） |
| 5 | `APK_SECRET` 已设强随机串（或保留 `data/secret.key`） |
| 6 | Gunicorn 或等价 WSGI 已配置 |
| 7 | Nginx/Caddy 反向代理已配置 |
| 8 | HTTPS 证书有效、自动续期已配置 |
| 9 | 防火墙仅放行 80/443 |
| 10 | 备份脚本可执行、定时备份已启用 |
| 11 | systemd 服务已启用（Linux） |
| 12 | 日志目录可写、磁盘空间充足 |

---

## 十二、常见问题

**Q: 外网访问不到？**  
检查防火墙、安全组、域名解析；确认 Nginx 监听 80/443 且反向代理到本机 5003。

**Q: 登录后刷新掉线？**  
确认 `PUBLIC_URL` 为 `https://...`，Session Cookie 才能正确设置 Secure。

**Q: 上传大文件失败？**  
检查 Nginx `client_max_body_size`、Flask `MAX_CONTENT_LENGTH`（默认 100MB）。

**Q: Gunicorn worker 被 OOM 杀掉？**  
减少 `workers` 或增加内存。

**Q: 定时备份未执行？**  
确认 `BACKUP_SCHEDULED=true`，应用持续运行；查看日志中是否有 “定时备份完成” 记录。
