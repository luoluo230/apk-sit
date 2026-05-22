# Cloud Deploy

默认场景：`Ubuntu / Debian` 云服务器。

## 一键部署

```bash
sudo bash scripts/cloud_deploy.sh
```

带域名的常见用法：

```bash
sudo PUBLIC_HOST=apk.example.com \
PUBLIC_URL=https://apk.example.com \
APP_USER=ubuntu \
bash scripts/cloud_deploy.sh
```

如果你想部署完成后自动申请 HTTPS：

```bash
sudo PUBLIC_HOST=apk.example.com \
PUBLIC_URL=https://apk.example.com \
ENABLE_HTTPS=1 \
CERTBOT_EMAIL=ops@example.com \
APP_USER=ubuntu \
bash scripts/cloud_deploy.sh
```

## 自动完成的事情

- 安装 `python3`、`venv`、`pip`、`nginx`、`git`
- 创建 `venv`
- 安装项目依赖
- 自动补齐 `.env`
- 创建 `systemd` 服务
- 启动 Gunicorn
- 配置 Nginx 反向代理
- 最后执行 `/health` 验证

## 可选参数

- `APP_USER`
- `APP_GROUP`
- `APP_NAME`
- `APP_PORT`
- `APK_DIR`
- `PUBLIC_HOST`
- `PUBLIC_URL`
- `ENABLE_NGINX`
- `ENABLE_UFW`
- `INSTALL_JENKINS_DEPS`
- `ENABLE_HTTPS`
- `CERTBOT_EMAIL`

## 常用命令

```bash
systemctl status apk-site.service
journalctl -u apk-site.service -f
systemctl restart apk-site.service
nginx -t
```

## 单独配置 HTTPS

如果你已经部署完成，只想补 HTTPS：

```bash
sudo PUBLIC_HOST=apk.example.com CERTBOT_EMAIL=ops@example.com bash scripts/setup_https.sh
```

## 本地一键上传并远程部署

```bash
SSH_HOST=1.2.3.4 \
SSH_USER=root \
REMOTE_APP_DIR=/opt/apk-site \
PUBLIC_HOST=apk.example.com \
PUBLIC_URL=https://apk.example.com \
ENABLE_HTTPS=1 \
CERTBOT_EMAIL=ops@example.com \
bash scripts/deploy_remote.sh
```

更多说明见 [docs/REMOTE_DEPLOY.md](./REMOTE_DEPLOY.md)
