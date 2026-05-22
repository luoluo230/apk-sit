# APK 下载中心 - 统一配置说明

所有可配置项集中在此目录的 `settings.json` 中，便于统一管理与维护。首次启动时若不存在 `settings.json`，将自动从 `settings.example.json` 复制生成。

## 配置优先级

1. **环境变量**（.env 或系统环境）- 最高优先级
2. **config/settings.json** - 项目级配置
3. **默认值** - 代码内置默认

敏感信息（如 JENKINS_TOKEN、数据库密码）建议仍使用 `.env` 或 `jenkins_credentials.json`，不要写入 settings.json。

## 配置项说明（中文）

### app - 应用基础
| 键 | 说明 | 默认 |
|---|---|---|
| port | 服务端口 | 5003 |
| host | 监听地址，0.0.0.0 表示本机及局域网可访问 | 0.0.0.0 |
| debug | 调试模式，生产环境务必 false | false |
| log_dir | 日志目录（相对项目根） | logs |

### apk - APK 存储
| 键 | 说明 | 默认 |
|---|---|---|
| dir | APK 包存放目录的绝对路径或相对路径 | /Users/xxx/Builds |

### jenkins - Jenkins 构建
| 键 | 说明 | 默认 |
|---|---|---|
| url | Jenkins 服务地址 | http://localhost:8080 |
| port | Jenkins 端口（url 未指定时用于拼接） | 8080 |
| job_name | 默认构建任务名 | Android |
| builds_dir | Jenkins 构建产物目录（相对项目根） | jenkins-clone/jobs/Android/builds |
| war_path | Jenkins war 包路径，空则自动查找 | "" |
| instances_dir | 多实例 Jenkins 数据目录 | data/jenkins_instances |
| default_user | 新建实例的默认用户名 | admin |
| default_password | 新建实例的默认密码 | admin123 |

**注意**：JENKINS_USER、JENKINS_TOKEN 请在 .env 或 jenkins_credentials.json 中配置。

### security - 安全与登录
| 键 | 说明 | 默认 |
|---|---|---|
| force_login | 是否强制登录 | true |
| inner_net | 内网网段前缀，逗号分隔 | 192.168.,10.,127. |
| ip_whitelist | IP 白名单，逗号分隔，留空不启用 | "" |
| login_attempts_limit | 登录失败次数上限 | 5 |
| login_lockout_minutes | 锁定分钟数 | 15 |

### external - 外网访问
| 键 | 说明 | 默认 |
|---|---|---|
| public_url | 公网完整 URL，用于二维码、邮件链接 | "" |
| external_domain | 仅域名时自动补协议 | "" |

### smtp - 定时报表邮件
| 键 | 说明 |
|---|---|
| host, port, user, password | SMTP 服务器 |
| report_email_to | 收件人 |
| report_hour | 每日发送小时（0-23） |

### feishu - 飞书告警
| 键 | 说明 |
|---|---|
| webhook | 飞书机器人 Webhook URL |
| disk_alert_gb | 磁盘不足告警阈值（GB） |

### workspace - 个人工作区
| 键 | 说明 |
|---|---|
| base_dir | 用户工作区文件存储根目录 | data/workspaces |

### docs - 文档模块
| 键 | 说明 |
|---|---|
| attachments_dir | 文档附件存储目录 | data/doc_attachments |
| max_attachment_mb | 单附件最大 MB | 20 |
