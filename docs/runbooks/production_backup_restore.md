# 生产数据备份与恢复

> Plan: P0-01 Step 6

## 备份范围

| 频率 | 路径 | 说明 |
|------|------|------|
| 每日 | `data/apk_site.db` | Release / Ops SQLite 主库 |
| 每日 | `data/projects.json` | 项目 JSON mirror（若启用双写） |
| 每日 | `data/jenkins_instances/` | Jenkins 实例配置（排除 `builds/` 运行时噪声） |
| 每周 | 整个 `data/` | 含 channels、versions、build_nodes mirror 等 |
| 按需 | OSS bucket | 由运维填写 bucket 与生命周期策略 |

**不要**将 `.env`、`jenkins_credentials.json`、`data/secret.key` 提交 git；备份文件应加密存储。

## 一键打包（Windows）

```powershell
powershell -File scripts/Backup-PortalData.ps1 -DryRun
powershell -File scripts/Backup-PortalData.ps1 -OutputDir D:\backups\apk-site
```

## 恢复步骤（概要）

1. 停止 Portal / Waitress 进程  
2. 还原 `data/apk_site.db` 与必要 JSON  
3. 还原 `data/jenkins_instances/{port}/` 配置（保留本地 builds 可选）  
4. 确认 `.env` Secret 与备份环境一致  
5. 启动 Portal，`GET /health` = ok  
6. 抽样：登录 Admin、打开 Release Journey、Jenkins 实例列表  

## 验证清单

- [ ] 备份脚本 `-DryRun` 列出预期文件  
- [ ] 备份包可在另一目录解压且文件完整  
- [ ] 恢复后 pytest smoke / 手动 Journey 预检可用  
