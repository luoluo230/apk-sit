# GM 运营中心封板验收说明

## 1. 闭环证据表
- 接口：`GET /api/gm-ops/closure-evidence`
- CI 接口：`GET /api/gm-ops/closure-evidence/ci`
- 目标：验证发布单关键字段是否具备“来源 -> 运行时生效”证据。

## 2. 质量门禁
- 接口：`GET /api/gm-ops/quality-gate`
- CI 接口：`GET /api/gm-ops/quality-gate/ci`
- 门禁项：
  - 发布预检（版本字段完整 + 网络档完整）
  - 闭环证据完整度（score == total）
  - Mongo/Redis 可达性

## 3. 自动化脚本
- 全链路报告：`scripts/gm_ops_e2e_check.ps1`
- CI 门禁脚本：`scripts/gm_ops_ci_gate.ps1`

示例：
```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\gm_ops_ci_gate.ps1 `
  -BaseUrl "http://127.0.0.1:5000" `
  -ProjectId "MyProject" `
  -Env "staging" `
  -Channel "test" `
  -Platform "android" `
  -VersionName "1.0.0" `
  -CiToken "your-ci-token"
```

## 4. 配置项
- `GM_CI_TOKEN`：CI 调用门禁接口的鉴权令牌（系统配置）。
- `MONGO_URI`：MongoDB 连接地址（用于运维可达性探测）。
- `REDIS_URI`：Redis 连接地址（用于运维可达性探测）。
