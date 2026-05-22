# APK 下载中心 · 商业级项目策划案

> 一次性补齐商业标准所缺失需求的项目计划。  
> 面向短期服务团队交付、长期平台化使用。

---

## 一、项目目标

| 目标 | 说明 |
|------|------|
| 商业标准 | 补齐测试、备份、监控、文档、错误页、i18n 基础 |
| 跨平台 | Windows / macOS 均可部署，无编译报错 |
| 界面友好 | 统一 404/500/403 页、响应式、文案清晰 |
| 可维护 | 文档齐全、依赖明确、结构清晰 |

---

## 二、阶段划分

### 阶段一：基础设施补齐（P0）

| 序号 | 任务 | 交付物 | 验收 |
|------|------|--------|------|
| 1.1 | 自动化测试框架 | `tests/`、`pytest`、`conftest.py` | `pytest tests/` 通过 |
| 1.2 | 健康检查与状态接口 | `/health`、`/api/status` | 返回 200 及基础统计 |
| 1.3 | 数据备份脚本 | `scripts/backup_data.py` | Windows/Mac 均可执行 |
| 1.4 | 统一错误页 | 404、500、403 模板 | 访问不存在的 URL 显示友好页 |
| 1.5 | API 文档页 | `/api/docs` | 列出主要接口说明 |
| 1.6 | 依赖与启动检查 | `requirements-dev.txt`、启动前校验 | 依赖安装无报错 |

### 阶段二：体验与规范（P1）

| 序号 | 任务 | 交付物 | 验收 |
|------|------|--------|------|
| 2.1 | i18n 目录与占位 | `translations/`、`_t()` 函数 | 可扩展多语言 |
| 2.2 | 备份定时调度 | 启动时注册备份任务 | 可配置备份间隔 |
| 2.3 | 日志格式规范 | 统一日志格式 | 便于排查 |
| 2.4 | 测试覆盖扩展 | `test_auth`、`test_api` | 核心流程有测试 |

### 阶段三：扩展与优化（P2）

| 序号 | 任务 | 交付物 | 验收 |
|------|------|--------|------|
| 3.1 | 登录接口限流 | 防暴力破解 | 超限返回 429 |
| 3.2 | OpenAPI 导出 | `openapi.json` | 可被 Swagger UI 加载 |
| 3.3 | 移动端优化 | 触控、字体 | 手机访问可用 |

---

## 三、任务明细

### 3.1 自动化测试（1.1）

**范围**：
- `tests/conftest.py`：创建 `app`、`client` fixture
- `tests/test_health.py`：`/health` 返回 200、`status: ok`
- `tests/test_auth.py`：登录页可访问、错误密码提示
- `tests/test_api.py`：`/api/apks` 等公开接口

**依赖**：`pytest`、`pytest-cov`（可选）

### 3.2 健康与状态（1.2）

**接口**：
- `GET /health`：保持现有 `{"status":"ok","service":"apk-site"}`
- `GET /api/status`：扩展版本，含 `stats`（用户数、项目数、APK 数等）

**注意**：`/health`、`/api/status` 可豁免 CSRF，供负载均衡/监控使用。

### 3.3 数据备份（1.3）

**脚本**：`scripts/backup_data.py`

**逻辑**：
1. 读取 `DATA_DIR`、`BACKUP_DIR`（可选 .env）
2. 创建 `backups/` 目录
3. 使用 `zipfile` 打包 `data/*.json`、`data/workspaces`、`data/project_icons`、`data/task_uploads`、`data/product_media`
4. 输出 `apk-site-YYYYMMDD-HHMMSS.zip`

**跨平台**：仅用 Python 标准库，不用 `tar`、`gzip` 等外部命令。

### 3.4 统一错误页（1.4）

**404**：简洁提示「页面不存在」，带返回首页/管理入口。

**500**：生产环境不展示堆栈，仅提示「服务异常，请稍后重试」。

**403**：提示「无权限访问」，引导登录或联系管理员。

**样式**：与主站一致（Tailwind、深色主题或白底）。

### 3.5 API 文档（1.5）

**路由**：`GET /api/docs`

**内容**：静态 HTML 页面，列出：
- 公开接口：`/api/apks`、`/api/stats`、`/health`、`/api/status`
- 需登录接口：说明需 Cookie/Session
- 构建、版本、Jenkins 等管理接口简要说明

### 3.6 依赖与启动检查（1.6）

**requirements-dev.txt**：
```
pytest>=7.0.0
pytest-cov>=4.0.0
```

**启动检查**（可选）：
- `data/` 目录存在
- `.env` 或必要配置存在
- 日志目录可写

---

## 四、实施顺序

```
1. 创建 tests/conftest.py、test_health.py
2. 创建 scripts/backup_data.py
3. 添加 /api/status、/api/docs
4. 注册 404、500、403 错误处理
5. 添加 requirements-dev.txt
6. 创建 translations/ 占位
7. 扩展 test_auth、test_api
8. 备份定时调度（可选）
```

---

## 五、风险与对策

| 风险 | 对策 |
|------|------|
| 测试修改生产数据 | 使用临时目录或 mock，不写入真实 data/ |
| 备份占用磁盘 | 可配置保留份数，自动清理旧备份 |
| 跨平台路径问题 | 一律 `os.path.join`，脚本在 Win/Mac 各测一轮 |
| 新增依赖冲突 | 新增依赖仅入 requirements-dev，生产不变 |

---

## 六、验收标准

- [ ] `pytest tests/` 全部通过
- [ ] `python scripts/backup_data.py` 在 Windows 和 Mac 均可执行并生成 zip
- [ ] 访问 `/nonexistent` 显示友好 404
- [ ] `/api/status` 返回合理统计
- [ ] `/api/docs` 可访问并展示接口列表
- [ ] 无编译/导入报错
- [ ] 界面文案清晰、无错别字
