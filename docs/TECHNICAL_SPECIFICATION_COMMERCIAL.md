# APK 下载中心 · 商业级技术方案

> 面向短期服务团队、长期平台化的商业项目标准技术规范。  
> 支持 **Windows** 与 **macOS** 跨平台部署，无编译报错，界面友好。

---

## 一、技术架构总览

### 1.1 分层架构

```
┌─────────────────────────────────────────────────────────┐
│                    展示层 (Presentation)                  │
│  SSR 模板 · Tailwind · 错误页 · 响应式布局 · i18n 占位   │
├─────────────────────────────────────────────────────────┤
│                    路由层 (Routes)                       │
│  Blueprint 模块化 · 权限装饰器 · 统一错误处理              │
├─────────────────────────────────────────────────────────┤
│                    服务层 (Services)                      │
│  Jenkins · 安全 · 启动 · 备份 · 监控                     │
├─────────────────────────────────────────────────────────┤
│                    数据层 (Models)                       │
│  JSON 持久化 · 业务辅助函数 · 审计日志                    │
├─────────────────────────────────────────────────────────┤
│                    基础设施 (Infrastructure)             │
│  配置(.env) · 日志 · 健康检查 · 跨平台路径               │
└─────────────────────────────────────────────────────────┘
```

### 1.2 技术栈

| 类别 | 技术选型 | 说明 |
|------|----------|------|
| 后端 | Flask 2.3+ | WSGI，单进程或 gunicorn 多进程 |
| 模板 | Jinja2 + Tailwind CSS | 服务端渲染，无 SPA 依赖 |
| 数据 | JSON 文件 | 单机、易迁移；后续可扩展 SQLite |
| 认证 | Session + CSRF | Flask-WTF |
| 跨平台 | `os.path` / `pathlib` | 统一使用 `os.path.join` 与正向斜杠 |
| Python | 3.8+ | 明确最低版本 |

### 1.3 跨平台规范（Windows / macOS）

| 项目 | 规范 | 实现要点 |
|------|------|----------|
| 路径 | 使用 `os.path.join()`、`pathlib.Path` | 禁止硬编码 `/` 或 `\` |
| 换行符 | 源码 LF，脚本兼容 CRLF | `.gitattributes` 设置 |
| 启动脚本 | `deploy.sh` (Mac/Linux)、`deploy.bat` (Windows) | 各自检测 Python、依赖 |
| 环境变量 | `.env` 统一格式 | 键值对，无平台差异 |
| 日志 | 按日期分文件 | `logs/app_YYYYMMDD.log` |
| 备份 | Python 脚本调用 | 不依赖 `tar`/`zip` 命令差异，用标准库 |

---

## 二、商业级补齐需求清单

### 2.1 自动化测试

| 需求 | 优先级 | 实现 |
|------|--------|------|
| 单元测试框架 | P0 | pytest |
| 健康检查接口测试 | P0 | `/health` 返回 200 |
| 登录流程测试 | P0 | 登录成功/失败、限流 |
| 权限校验测试 | P1 | `can_view_project`、`admin_required` |
| 数据层读写测试 | P1 | `load_json`、`save_json` |
| 构建触发 API 测试 | P2 | Mock Jenkins |

**目录结构**：
```
tests/
  conftest.py      # fixture、app client
  test_health.py   # 健康检查
  test_auth.py     # 认证
  test_api.py      # 公开 API
```

### 2.2 数据备份

| 需求 | 优先级 | 实现 |
|------|--------|------|
| 手动备份脚本 | P0 | `scripts/backup_data.py` |
| 定时备份调度 | P1 | 启动时注册调度任务 |
| 备份目标可配置 | P1 | `.env` 中 `BACKUP_DIR` |
| 跨平台 | P0 | 仅用 Python 标准库 `shutil`、`zipfile` |

**备份范围**：`data/*.json`、`data/workspaces`、`data/project_icons`、`data/task_uploads`、`data/product_media` 等。

### 2.3 API 文档与监控

| 需求 | 优先级 | 实现 |
|------|--------|------|
| API 列表页 | P0 | `/api/docs` 静态 HTML 文档 |
| 扩展健康检查 | P0 | `/api/status` 含基础统计 |
| 接口限流（可选） | P2 | 登录接口限流 |
| OpenAPI 规范 | P2 | 可导出 `openapi.json` |

**`/api/status` 返回示例**：
```json
{
  "status": "ok",
  "service": "apk-site",
  "stats": {
    "users": 5,
    "projects": 3,
    "apk_count": 12
  },
  "version": "1.0"
}
```

### 2.4 错误页与界面友好

| 需求 | 优先级 | 实现 |
|------|--------|------|
| 404 友好页 | P0 | 统一 404 模板 |
| 500 友好页 | P0 | 统一 500 模板，不泄露堆栈 |
| 403 无权限页 | P0 | 提示登录或联系管理员 |
| 移动端基础适配 | P1 | 已有 Tailwind 响应式，补充 meta viewport |

### 2.5 国际化（i18n）基础

| 需求 | 优先级 | 实现 |
|------|--------|------|
| i18n 目录结构 | P0 | `translations/zh_CN/`、`en/` |
| 文案抽取占位 | P1 | `_t('key')` 函数 |
| 语言切换（可选） | P2 | Session 存储，预留接口 |

**目录**：
```
translations/
  zh_CN/
    messages.json
  en/
    messages.json
```

### 2.6 依赖与构建

| 需求 | 优先级 | 实现 |
|------|--------|------|
| 依赖锁定 | P0 | `requirements.txt` 固定版本 |
| 开发依赖分离 | P1 | `requirements-dev.txt` |
| 启动前检查 | P1 | 检查必需目录、配置文件 |

### 2.7 日志与可观测

| 需求 | 优先级 | 实现 |
|------|--------|------|
| 结构化日志格式 | P1 | 时间、级别、模块、消息 |
| 请求 ID（可选） | P2 | 便于排查 |
| 错误堆栈不落生产 | P0 | DEBUG=false 时 500 页不展示堆栈 |

---

## 三、实现规范

### 3.1 测试

- 使用 `pytest`，入口：`pytest tests/ -v`
- Fixture 提供 `app`、`client`
- 不修改生产 `data/`，测试用临时目录或 mock

### 3.2 备份脚本

- 入口：`python scripts/backup_data.py`
- 输出：`backups/apk-site-YYYYMMDD-HHMMSS.zip`
- 可配置 `BACKUP_DIR`、`DATA_DIR`

### 3.3 错误处理

```python
@app.errorhandler(404)
def not_found(e):
    return render_template_string(ERROR_404_HTML), 404
```

### 3.4 路径规范

```python
import os
BASE = os.path.dirname(os.path.abspath(__file__))
path = os.path.join(BASE, 'data', 'file.json')
path = os.path.normpath(path)  # 统一格式
```

---

## 四、兼容性矩阵

| 环境 | Python | 操作系统 | 说明 |
|------|--------|----------|------|
| 生产 | 3.8+ | Windows 10+ | 已验证 |
| 生产 | 3.8+ | macOS 12+ | 已验证 |
| 生产 | 3.8+ | Linux (Ubuntu 20+) | 理论支持 |
| 开发 | 3.8+ | 同上 | venv 推荐 |

---

## 五、部署清单（商业级）

1. 复制项目 → 创建 `.env`
2. `pip install -r requirements.txt`
3. `python scripts/backup_data.py`（可选，验证备份）
4. Mac/Linux：`./deploy.sh start`
5. Windows：`deploy.bat` 选 1 启动
6. 外网：配置 `PUBLIC_URL`，前置 Nginx/Caddy HTTPS

---

## 六、后续扩展预留

- **数据库**：预留 `models/db.py`，可接入 SQLite
- **开放 API**：`/api/v1/` 前缀，Token 鉴权
- **多租户**：`tenant_id` 字段预留
- **前端 SPA**：可单独部署 Vue/React，API 已就绪
