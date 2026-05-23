# Remote Deploy

这个脚本用于“本地一条命令上传代码到服务器并触发远程部署”。

脚本：
[scripts/deploy_remote.sh](F:\apk-site\scripts\deploy_remote.sh)

## 最小用法

```bash
SSH_HOST=1.2.3.4 SSH_USER=root bash scripts/deploy_remote.sh
```

## 常见完整用法

```bash
SSH_HOST=1.2.3.4 \
SSH_USER=root \
SSH_PORT=22 \
REMOTE_APP_DIR=/opt/apk-site \
PUBLIC_HOST=apk.example.com \
PUBLIC_URL=https://apk.example.com \
APP_USER=ubuntu \
ENABLE_HTTPS=1 \
CERTBOT_EMAIL=ops@example.com \
bash scripts/deploy_remote.sh
```

## 它会做什么

1. 用 `rsync` 上传项目；如果本地没有 `rsync`，自动回退到 `tar + scp`
2. 远程进入项目目录
3. 调用 `scripts/cloud_deploy.sh`
4. 自动安装依赖、配置 `systemd`、配置 Nginx
5. 如果开启 `ENABLE_HTTPS=1`，会自动申请证书并开启 HTTPS

## 需要你提前准备

- 本地能 `ssh` 到服务器
- 服务器有 `sudo` 权限
- 域名已解析到服务器公网 IP
- 80/443 端口已放行
