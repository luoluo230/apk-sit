# iOS 生产签名与 TestFlight Runbook（C-P1-4 / P2-02 Step 5）

本 runbook 覆盖 **iOS 商业管线** 从 Xcode archive → 签名 export → OSS 备份 → TestFlight 上传。

---

## 前置

| 项 | 说明 |
|----|------|
| 构建机 | macOS + Xcode + Unity iOS module |
| 证书 | Apple Developer Team ID、Distribution 证书 (.p12) 或 ASC API Key |
| Portal | 版本组 `meta.ios_signing` 已配置（Web UI 或 API） |
| Jenkins | `commercial_ios_pipeline.sh` 已挂载 `jenkins-clone/scripts` |

---

## 1. Portal 配置 ios_signing

版本组 metadata 示例：

```json
{
  "ios_signing": {
    "mode": "upload",
    "team_id": "ABCDE12345",
    "bundle_id": "com.example.gomeku",
    "asc_api_key_id": "XXXXXXXXXX",
    "asc_api_issuer": "xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx",
    "asc_api_key_path": "/secure/AuthKey_XXXXXXXXXX.p8"
  }
}
```

字段规范化见 `services/build/platform_signing_service.py`。

---

## 2. Jenkins 环境变量

管线启动前导出（可用 helper 脚本）：

```bash
# 从 JSON 或已有 env 生成 export 行
python3 jenkins-clone/scripts/resolve_ios_signing_env.py
# 或手动：
export IOS_EXPORT_METHOD=app-store   # app-store | ad-hoc | development | enterprise
export IOS_TEAM_ID=ABCDE12345
export IOS_SIGNING_BUNDLE_ID=com.example.gomeku
export ASC_API_KEY_ID=...
export ASC_API_ISSUER=...
export ASC_API_KEY_PATH=/path/AuthKey.p8
export EXTERNAL_UPLOAD_TESTFLIGHT=true
```

---

## 3. 管线步骤（commercial_ios_pipeline.sh）

1. **Steps 1–3** — 与 Android 共用 `commercial_android_pipeline.sh`（资源/配置/code）
2. **Step 5** — `iOSBuildScript.ExportXcodeFromCommandLine` 导出 Xcode 工程
3. **Step 6** — `XcodeArchiveCli.ExportIpaFromCommandLine`
   - 读取 `-exportMethod` / `IOS_EXPORT_METHOD`
   - 生成 `ExportOptions.plist`（app-store / ad-hoc / development）
   - 输出 `IPA_FILE` 环境变量
4. **Step 7** — `archive_build_artifact.py` OSS 备份
5. **Step 8** — `upload_testflight.py`（需 ASC API Key；未配置则 SKIP）

---

## 4. 本地验证

```bash
# Unity batchmode archive（在项目根目录）
Unity -batchmode -quit -executeMethod XcodeArchiveCli.ExportIpaFromCommandLine \
  -appName GomeKu -releaseVersion 1.0.0 -versionCode 1 \
  -exportMethod app-store -teamId ABCDE12345 -bundleId com.example.gomeku

echo "IPA_FILE=$IPA_FILE"
python3 jenkins-clone/scripts/upload_testflight.py
```

---

## 5. 故障排查

| 现象 | 处理 |
|------|------|
| `IPA not found` | 检查 `BuildOutput/iOS/{appName}/ipa/` 与 xcodebuild 日志 |
| 签名失败 | 确认 `IOS_TEAM_ID`、描述文件与 bundle id 一致 |
| TestFlight SKIP | 配置 `ASC_API_*` 三件套；需在 macOS 上运行 |
| export method 错误 | production 用 `app-store`；内测 ad-hoc 用 `ad-hoc` |

---

## 6. 相关文件

| 文件 | 用途 |
|------|------|
| `maclient/Assets/Editor/ReleaseTools/XcodeArchiveCli.cs` | archive + export IPA |
| `jenkins-clone/scripts/commercial_ios_pipeline.sh` | Jenkins 入口 |
| `jenkins-clone/scripts/upload_testflight.py` | TestFlight 上传 |
| `jenkins-clone/scripts/resolve_ios_signing_env.py` | 签名 env 解析 |
| `portals/common/core/scripts/verify_hotupdate_config_checksum.py` | HotUpdateConfig 与 Portal 对齐 |

---

## C-P1-4 关闭标准

- [x] `XcodeArchiveCli` 支持 app-store / ad-hoc ExportOptions
- [x] 管线传入 `ios_signing` → env → xcodebuild
- [x] TestFlight upload 脚本与 ASC secret 联动（配置则上传，否则 SKIP）
- [ ] 生产 Jenkins 手动跑通一次（需 macOS 构建机 + 有效证书）
