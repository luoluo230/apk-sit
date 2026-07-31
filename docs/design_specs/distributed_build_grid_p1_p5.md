# 分布式构建网格 P1–P5 实施规格（定稿）

更新时间：2026-07-24  
状态：实施中  
权威拓扑：**5 台独立机器 + 运行面可扩展**

## 拓扑

| # | 角色 | OS | Jenkins Label | Job |
|---|------|-----|---------------|-----|
| 0 | 控制面 | Windows | — | Master |
| 1 | Android 构建 | Windows | `build-android` | `Android` |
| 2 | iOS 构建 | macOS | `build-ios` | `iOS` |
| 3 | 小游戏构建 | Windows | `build-wxminigame` | `WxMinigame` |
| 4+ | 运行面 | Win/Linux | `runtime-*` | — |

## 决策固化

1. 小游戏第一期整包重发；工具链：微信 **WX-WASM-SDK-V2** + `DoExport`
2. Android/iOS/WebGL **同一 Unity 版本**，Portal 构建前门禁
3. iOS 签名：创建/编辑版本时 Web 上传 p12/profile 或指定路径，构建时注入 Mac 节点
4. 微信 AppID 可空创建、后期编辑；`miniprogram-ci` 上传可选
5. 构建机四角色 + 控制面第五台，**禁止混跑**
6. 产物：**local 落盘 → OSS 备份 → 外部分发**（iOS TestFlight、小游戏微信后台）

## 产物流

```text
构建完成 → data/artifacts/{project}/{scope}/{build_id}/
         → OSS {ProjectRoot}/{Env}/{Channel}/{Platform}/artifacts/...
         → external (TestFlight / 微信后台)
         → webhook → ReleaseOrder artifacts_ready
```

## 平台 ID

| platform | artifact_type | 底包步骤 |
|----------|---------------|----------|
| android | apk | GameKuAndroidBuildScript + ApkReleaseUploadCli |
| ios | ipa | iOSBuildScript + XcodeArchiveCli + TestFlight |
| wechat_minigame | wxgame_bundle | WxMinigameExportCli + 可选 miniprogram-ci |

## 安装入口

- Windows: `scripts/Install-ReleasePlatform.ps1 -Role control|build-android|build-wxminigame`
- macOS: `scripts/install_release_platform.sh --role build-ios`
- Agent 注册: `POST /api/internal/build-nodes/heartbeat`

## 阶段验收

- **P1**: 五角色安装脚本 + 构建节点 API/UI + Jenkins 三 Job + label
- **P2**: Android 仅 `build-android` + artifact landing
- **P3**: iOS 签名配置 + pipeline + maclient iOS CLIs + TestFlight
- **P4**: wechat_minigame 平台 + pipeline + maclient Wx CLIs
- **P5**: Journey/构建触发按 platform 路由 + 节点/Unity 门禁
