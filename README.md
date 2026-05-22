# APK 下载中心

APK 包展示、下载、二维码、构建管理、项目管理与任务协同的 Web 应用，支持 Jenkins 集成与多实例、数据分析、版本管理。按商业项目标准开发，支持 **Windows** 与 **macOS** 跨平台部署。

## 快速开始

1. **配置**：复制 `.env.example` 为 `.env`，按需修改（至少 `APK_DIR`、`APK_PORT`）。
2. **依赖**：`pip install -r requirements.txt`
3. **启动**：
   - Mac/Linux：`./deploy.sh start` 或 `./deploy.sh menu`
   - Windows：运行 `deploy.bat` 选择 1 直接启动

默认管理员：`admin` / `admin123`。

## 测试与备份

- **基础测试**（无需额外依赖）：`python -m unittest tests.test_basic`
- **完整测试**（需 pytest）：`pip install -r requirements-dev.txt && pytest tests/ -v`
- **数据备份**：`python scripts/backup_data.py`，输出至 `backups/`

## 文档

| 文档 | 说明 |
|------|------|
| [docs/DEPLOY.md](docs/DEPLOY.md) | 部署与迁移、外网访问、HTTPS 与安全 |
| [docs/PRODUCTION_CHECKLIST.md](docs/PRODUCTION_CHECKLIST.md) | 商业级生产清单（兼容性、可配性、安全、可迁移性） |
| [docs/TECHNICAL_SPECIFICATION_COMMERCIAL.md](docs/TECHNICAL_SPECIFICATION_COMMERCIAL.md) | 商业级技术方案（跨平台、测试、备份、API 文档） |
| [docs/PROJECT_PLAN_COMMERCIAL.md](docs/PROJECT_PLAN_COMMERCIAL.md) | 商业级项目策划案 |
| [README_ARCHITECTURE.md](README_ARCHITECTURE.md) | 架构与模块说明 |

## 外网与安全

- 外网访问：在 `.env` 中配置 `PUBLIC_URL=https://你的域名`，并前置 Nginx/Caddy 做 HTTPS 反向代理。
- 健康检查：`GET /health` 返回 `{"status":"ok"}`，可用于负载均衡探测。

详见 [docs/DEPLOY.md](docs/DEPLOY.md)。

## Runtime Entrypoint Contract (2026-05-15)
- The only supported runtime chain is: `app_new.py + *_wsgi.py`.
- Admin startup: `waitress admin_wsgi:app`
- Player startup: `waitress player_wsgi:app`
- Forum startup: `waitress forum_wsgi:app`
- `app.py` is deprecated and blocked as runtime entry.

Quick checks:
- `python scripts/check_entrypoint_consistency.py`
- `powershell -ExecutionPolicy Bypass -File scripts/runtime_entry_diagnose.ps1`
- Logged-in diagnostic endpoint: `/internal/runtime/entrypoint`
