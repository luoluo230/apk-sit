# APK 下载中心 - 商业级生产清单

本文档为「兼容性、可操作性、美观、可配性、可迁移性、安全与外网访问」的完整实现清单。**仅做增量修改，不减少现有功能。**

---

## 一、配置与可迁移性

| # | 项 | 说明 | 状态 |
|---|---|----|------|
| 1.1 | 统一配置文件 | 应用只读 `.env`（由 config.py 加载），部署脚本不再使用 config.env | ✅ |
| 1.2 | 完整 .env.example | 含 APK_DIR、APK_PORT、APK_HOST、APK_SECRET、PUBLIC_URL、Jenkins、SMTP、飞书等 | ✅ |
| 1.3 | 外网域名/公网访问地址 | 新增 PUBLIC_URL / EXTERNAL_DOMAIN，用于外网访问时的基准 URL、邮件/二维码链接 | ✅ |
| 1.4 | 跨平台路径 | 使用 os.path.join / pathlib，避免硬编码 / 或 \ | ✅ |
| 1.5 | 首次运行自动创建 .env | 无 .env 时从 .env.example 复制并提示用户修改 | ✅ |

---

## 二、部署与一键运行

| # | 项 | 说明 | 状态 |
|---|---|----|------|
| 2.1 | 单配置文件 | 部署脚本只依赖 .env（从 .env.example 生成若不存在） | ✅ |
| 2.2 | 最少命令部署 | 文档明确：复制项目 → 创建/编辑 .env → pip install -r requirements.txt → ./deploy.sh 或 deploy.bat | ✅ |
| 2.3 | deploy.sh (Mac/Linux) | 检测 Python3、依赖；无 .env 时从 .env.example 复制；start/stop/restart/autostart | ✅ |
| 2.4 | deploy.bat (Windows) | 检测 Python、依赖；无 .env 时从 .env.example 复制；同上菜单 | ✅ |
| 2.5 | requirements.txt | 固定版本，包含 Flask、qrcode、Pillow 等，无多余依赖 | ✅ |

---

## 三、安全加固（含外网暴露）

| # | 项 | 说明 | 状态 |
|---|---|----|------|
| 3.1 | 安全响应头 | X-Frame-Options, X-Content-Type-Options, X-XSS-Protection, Referrer-Policy 等 | ✅ |
| 3.2 | Session 安全 | Cookie 设置 HttpOnly、SameSite；在 HTTPS 环境下 Secure | ✅ |
| 3.3 | 登录限流 | 已有 IP 登录尝试限制与锁定时长（可配置） | 已有 |
| 3.4 | 生产环境关闭 DEBUG | 通过 .env APK_DEBUG=false 控制 | 已有 |
| 3.5 | 密钥管理 | SECRET_KEY 来自 APK_SECRET 或 data/secret.key，不写死 | 已有 |
| 3.6 | 上传/请求体大小限制 | MAX_CONTENT_LENGTH 已设 | 已有 |
| 3.7 | HTTPS 反向代理说明 | 文档说明外网建议用 Nginx/Caddy 做 HTTPS 与反向代理 | ✅ |

---

## 四、兼容性

| # | 项 | 说明 | 状态 |
|---|---|----|------|
| 4.1 | Python 版本 | 明确要求 Python 3.8+ | ✅ |
| 4.2 | Windows/Mac 启动脚本 | start.bat 与 start.sh 均指向 app_new.py，路径与命令兼容 | 已有 |
| 4.3 | 编码与换行 | 源码 UTF-8；脚本注意换行符（LF/CRLF） | 已有 |

---

## 五、可操作性

| # | 项 | 说明 | 状态 |
|---|---|----|------|
| 5.1 | 启动信息 | 控制台输出本地/局域网/公网（若配置 PUBLIC_URL）访问地址 | ✅ |
| 5.2 | 健康检查 | 可选 /health 供负载均衡/监控探测 | ✅ |
| 5.3 | 日志 | 已有按日期与文件分类日志 | 已有 |

---

## 六、功能与模块（仅增量）

| # | 项 | 说明 | 状态 |
|---|---|----|------|
| 6.1 | 安全中间件 | 统一注入安全头、Session 安全配置 | ✅ |
| 6.2 | 外网域名展示 | 配置 PUBLIC_URL 后，启动信息、二维码链接、.apk-site-base-url 均使用公网地址 | ✅ |
| 6.3 | 不删减现有功能 | 所有既有模块与路由保留 | 已有 |

---

## 七、文档

| # | 项 | 说明 | 状态 |
|---|---|----|------|
| 7.1 | DEPLOY.md | 部署与迁移步骤、.env 说明、外网与 HTTPS 建议 | ✅ |
| 7.2 | .env.example 注释 | 每个变量简要说明用途与示例 | ✅ |

---

## 使用与迁移流程（目标）

1. **复制项目**到新机器（Windows 或 Mac）。
2. **配置**：若没有 `.env`，复制 `.env.example` 为 `.env`，按需修改（至少 APK_DIR、可选 PUBLIC_URL、Jenkins 等）。
3. **安装依赖**：`pip install -r requirements.txt`（建议使用 venv）。
4. **启动**：  
   - Mac/Linux：`./deploy.sh start` 或 `./deploy.sh menu`  
   - Windows：`deploy.bat` 选 1 直接启动。
5. **外网访问**：配置 PUBLIC_URL，前置 Nginx/Caddy 做 HTTPS，详见 DEPLOY.md。
