# Runbook：Portal → Jenkins → Publish → 客户端选版

正式上线唯一路径。maclient Editor 本地上传仅作测试旁路。

## 正式闭环

1. **项目管理**：确认项目有 `game_id` / `game_key`（编辑项目 → 接入凭据，只读可复制）。
2. **版本组**：配置四步管线 + Jenkins 实例/Job + bootstrap 模板字段。
3. **创建 VersionCode**（env × channel × platform）。
4. **发布单 / quick-build**：Portal 触发构建；Jenkins 参数必须含 `GAME_ID`、`GAME_KEY`（缺凭据会阻断）。
5. **Jenkins**：`commercial_android_pipeline.sh` 在 APK 前执行 `HotUpdateConfigSyncCli` 写入凭据与 `PreferUnifiedBootstrap`。
6. **Publish**：激活 Scope 上 Bundle（不是 Editor 本地激活）。
7. **客户端**：`GET /api/public/runtime-bootstrap?game_id=&game_key=&env_key=&channel=&platform=` 拿到 active Bundle 路径后拉热更。

## 测试旁路

- Unity「商业发布工作台」可本地上传 OSS，UI 已标注「仅测试」。
- 测试上传**不能**替代 Portal Publish；玩家包只认 bootstrap 返回的 Bundle。

## 故障对照

| 现象 | 排查 |
|------|------|
| 触发构建报缺少 game_id/game_key | 项目管理生成/确认接入凭据后重试 |
| Jenkins Step4-pre ERROR GAME_ID/GAME_KEY | Portal 未注入参数；检查 Job 参数与 `plan_to_jenkins_params` |
| bootstrap 401/项目未命中 | 包内 GameId/GameKey 与 Portal 不一致；重跑 SyncCli / DevStack sync |
| bootstrap 204 | 灰度未命中（device/user 不在 rollout） |
| bootstrap 有响应但无资源 | Bundle 未 Publish / `catalog_file_name` 或 relative_path 空 |
| 仍走 version-resolve | 确认 `PreferUnifiedBootstrap=1` 且正式包未开 OSS fallback |

## 快速验收

```powershell
# 1) 参数含凭据（单测）
cd portals\common\core
py -3 -m unittest tests.test_release_build_identity -v

# 2) 本机同步凭据进 maclient
powershell -ExecutionPolicy Bypass -File scripts\Sync-DevStackClientConfig.ps1

# 3) Publish 后（替换真实凭据与 scope）
curl "http://127.0.0.1:5003/api/public/runtime-bootstrap?game_id=...&game_key=...&env_key=development&channel=wechat&platform=android"
```

详见 [client_bootstrap_contract.md](../client_bootstrap_contract.md)。
