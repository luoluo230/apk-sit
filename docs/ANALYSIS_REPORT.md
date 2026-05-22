# APK 下载中心 · 项目分析报告

> 编译错误、BUG、长期商业成熟度评估

---

## 一、编译与导入

| 项 | 状态 |
|----|------|
| Python 导入 | ✅ `from app_new import app` 无报错 |
| Linter | ✅ 无静态检查错误 |
| 单元测试 | ✅ 17 个测试全部通过 |

---

## 二、已修复问题

### 2.1 test_health.py 依赖 pytest 导致 unittest discover 失败

- **问题**：`import pytest` 在未安装 pytest 时导致 `ModuleNotFoundError`
- **修复**：改为 unittest 风格，与 test_auth、test_api 一致，实现「unittest + pytest 双支持」

### 2.2 上传 APK 路径穿越风险

- **问题**：`file.filename` 可能含 `../` 等路径，直接拼接 `Config.APK_DIR` 存在路径穿越
- **修复**：使用 `os.path.basename(file.filename)` 仅取文件名，防止写入目录外路径

---

## 三、安全与健壮性

### 3.1 已具备

| 项 | 说明 |
|----|------|
| SQL 注入防护 | models/db.py 使用参数化查询 `(?,?,...)` |
| 下载路径校验 | download/pub_download 检查 `..`、`/`，使用 `basename` |
| 项目图标/任务附件 | admin_routes 校验 `..`、`/`、`\` |
| 产品媒体 | products_public 使用 `secure_filename` |
| 登录限流 | 429 + Retry-After |
| Session / CSRF | Flask-WTF、安全头 |
| 审计日志 | 关键操作双写 JSON + SQLite |

### 3.2 待关注（非阻塞）

| 项 | 说明 |
|----|------|
| app.py 裸 except | 旧版入口，主入口为 app_new.py，影响有限 |
| pub/download 无登录 | 公开下载设计如此，需在部署层控制访问（如 Nginx 限 IP） |

---

## 四、长期商业用成熟度

### 4.1 已满足

| 维度 | 能力 |
|------|------|
| 数据持久化 | JSON + SQLite 可选、迁移脚本 |
| 监控与可观测 | 请求 ID、性能统计、结构化日志 |
| 安全 | 限流、审计、路径校验、Session 安全 |
| 备份与恢复 | 定时备份、保留策略、手动备份脚本 |
| API 开放 | OpenAPI、/api/status、Webhook |
| 多租户 | tenant_id 预留 |
| 测试 | 17 个用例覆盖健康、API、认证、限流 |
| 文档 | 技术方案、策划案、API 文档 |

### 4.2 可选增强（按需）

| 项 | 优先级 | 说明 |
|----|--------|------|
| 审计日志从 SQLite 读取 | P2 | 启用 USE_SQLITE 时管理端可从 DB 读 |
| 项目列表按 tenant_id 过滤 | P2 | 多租户隔离完整化 |
| 依赖版本锁定 | P2 | cryptography 使用 >=，可改为精确版本 |
| 集成测试 / E2E | P2 | 核心流程端到端验证 |
| 生产部署建议 | P1 | gunicorn、Nginx、HTTPS 等部署清单 |

---

## 五、结论

- **编译 / 运行**：无错误，可直接运行。
- **已知 BUG**：上传路径穿越与 test_health 导入问题已修复。
- **长期商业用**：已具备 SQLite、限流、Webhook、监控、备份等商业级基础，可按需补充上述可选增强。
