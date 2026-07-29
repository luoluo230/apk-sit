# 项目 Onboarding 向导 Runbook

Plan: P1-02 — 新项目从 0 到首次 quick-build。

## 入口

- **UI 向导**：`/admin/projects/new/wizard`（项目列表 →「向导创建」）
- **API**：`POST /api/admin/projects/onboard`（需 `projects` 权限）

## 前置条件

1. P0-02 配置注册表已启用（SQLite + registry accessors）
2. 全局渠道目录中已存在目标渠道 ID
3. Jenkins 实例在线（若需立即 quick-build）
4. 操作账号为 admin / super_admin，或为项目 `editors`

## API 示例

```bash
curl -X POST http://127.0.0.1:5000/api/admin/projects/onboard \
  -H "Content-Type: application/json" \
  -b "session=..." \
  -d '{
    "name": "GomeKu",
    "id": "GomeKu",
    "git_url": "git@example.com/maclient.git",
    "unity_project_path": "E:/maclient",
    "channels": ["1001"],
    "platforms": ["android"],
    "env_keys": ["development", "testing"],
    "jenkins_instance_id": "8082",
    "seed_version_group": {
      "version_name": "1.0.0",
      "env_key": "development",
      "channel_id": "1001",
      "platform": "android"
    }
  }'
```

成功响应包含 `project_id`、`version_id`、`scope_ids` 与 `next_actions` 链接。

## 向导步骤（UI）

1. 基本信息 → 2. Git/Unity → 3. 渠道/平台 → 4. 环境 → 5. Jenkins → 6. 首版本 → 7. 确认

完成后按 `next_actions` 进入：

- 版本管线配置：`/admin/projects/{id}/versions`
- Dev Runtime：`/admin/projects/{id}/ops`
- Build Journey：`/admin/projects/{id}/environments/{env}/channels/{channel}/build`

## 加渠道（已有项目）

`POST /admin/projects/{id}/channels/assign`

```json
{
  "channel_ids": ["1002"],
  "copy_version_rows": true
}
```

响应 `docs.client_bootstrap_contract` 指向客户端 bootstrap 映射文档。

## DevStack 可选 seed

```powershell
.\scripts\Start-DevStack.ps1 -OnboardProject -OnboardPayloadFile .\tmp\onboard-gomeku.json
```

需本地 Portal 已启动且 session cookie 可用。

## 验收（熟练工程师 ≤30 分钟）

1. 走完向导或调用 onboard API
2. 打开 Build Journey，确认 delivery line 可见
3. Jenkins 在线时触发 quick-build
4. 失败时确认无残留 project（API 自动 rollback）

## 相关测试

```bash
cd portals/common/core
py -m pytest tests/test_project_onboarding.py -q
node --check static/project_onboarding.js
```
