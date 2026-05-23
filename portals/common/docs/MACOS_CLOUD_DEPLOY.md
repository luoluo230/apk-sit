# macOS 一键部署

在 macOS 上可以直接运行：

```bash
bash scripts/cloud_deploy_macos.sh
```

常用参数：

```bash
ADMIN_PORT=5003 PLAYER_PORT=5004 APK_DIR="$PWD/jenkins-clone/workspace/Android" bash scripts/cloud_deploy_macos.sh
```

脚本会自动完成：

- 创建 `venv`
- 安装 `requirements.txt` 和 `requirements-prod.txt`
- 将 JSON 数据迁移到 SQLite
- 写入 `.env`
- 通过 `launchd` 注册并常驻启动管理端和玩家端
- 将日志输出到 `logs/admin-portal.log` 和 `logs/player-portal.log`

卸载：

```bash
launchctl unload ~/Library/LaunchAgents/com.apksite.admin.plist
launchctl unload ~/Library/LaunchAgents/com.apksite.player.plist
```
