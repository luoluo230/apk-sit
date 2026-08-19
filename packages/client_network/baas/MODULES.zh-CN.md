# BaaS 客户端业务模块说明

命名空间：`MAClient.Network.Baas`  
程序集：`MAClient.Network.Baas.asmdef`

所有业务 Client 实现 `IBaasFeatureClient`，通过 `BaasFeatureHub` 获取。功能开关与服务端 `registry.FEATURE_CATALOG` 对齐。

---

## 核心层（必用）

| 类 | 说明 |
|----|------|
| `BaasBootstrapService` | 调用 Portal bootstrap，填充 `BaasClientContext`，可选自动游客登录 |
| `BaasFeatureHub` | 业务模块统一入口；未开通功能访问时抛出异常 |
| `BaasClientContext` | 会话、Header、端点表、FeatureFlags |
| `BaasNetworkSettings` | Inspector / Resources 配置 |
| `BaasApiResponse<T>` | HTTP 响应解析、错误码、中文 UserMessage |
| `BaasCoroutineHelper` | 协程调用包装，避免 null 响应 |
| `BaasHttp` | UnityWebRequest 封装 |

---

## 业务模块

### 账号 — `BaasAuthClient`（login）

- **前置**：服务级 Header（bootstrap 后即有）
- **典型流程**：`GuestLoginAsync` → Context 自动写入 token / player_id
- **服务端**：`auth_service.py`

### 公告 — `BaasAnnounceClient`（announce）

- **典型流程**：`ListActiveAsync`
- **服务端**：`announce_service.py`

### 邮件 — `BaasMailClient`（mail）

- **典型流程**：`ListInboxAsync` → `ClaimAsync`
- **服务端**：`mail_service.py`

### 云存档 — `BaasCloudSaveClient`（cloudsave）

- **典型流程**：`GetAsync` / `PutAsync`（KV）
- **服务端**：`cloudsave_service.py`

### 排行榜 — `BaasLeaderboardClient`（leaderboard）

- **典型流程**：`SubmitScoreAsync` → `GetBoardAsync`
- **服务端**：`retention_services.py`

### 商城 — `BaasShopClient`（economy）

- **典型流程**：`GetWalletAsync` → `ListProductsAsync` → `PurchaseAsync`
- **服务端**：`retention_services.py`

### 成就 — `BaasAchievementClient`（achievement）

- **典型流程**：`ListAsync` → `ReportProgressAsync` → `ClaimAsync`
- **服务端**：`retention_services.py`

### 礼包 — `BaasGiftClient`（gift）

- **典型流程**：`RedeemCodeAsync`
- **服务端**：`retention_services.py`

### 公会 — `BaasGuildClient`（guild）

- **典型流程**：`CreateAsync` / `JoinAsync` / `GetMyGuildAsync`
- **服务端**：`social_services.py`

### 战令 — `BaasBattlePassClient`（battlepass）

- **典型流程**：`GetStatusAsync` → `AddXpAsync` → `ClaimLevelAsync`
- **服务端**：`social_services.py`

### 周期任务 — `BaasTaskClient`（periodic_task）

- **典型流程**：`ListTasksAsync` → `ReportProgressAsync` → `ClaimAsync`
- **服务端**：`social_services.py`

### 防沉迷 — `BaasComplianceClient`（compliance）

- **典型流程**：`StartSessionAsync` → 定时 `HeartbeatAsync`
- **服务端**：`compliance_service.py`

### PVE 推图 — `BaasPveClient`（pve）

- **典型流程**：
  1. `GetStaminaAsync` / `GetProgressAsync`
  2. `StartBattleAsync(stageId, teamJson)` → 获得 `seed`、`battle_id`
  3. 客户端演算（可用 `BaasSeedBattleSimulator` 或自研 BattleFoundation）
  4. `SettleBattleAsync(..., checksum, replayHash, replayTicks)`
- **反作弊**：`BuildChecksum` / `BuildReplayHash` 须与服务端 `battle_antifraud.py` 一致
- **配置键**：`feature_configs.pve`（heroes, stages, anti_cheat, stamina）
- **服务端**：`pve_service.py`

### 异步竞技场 — `BaasArenaClient`（arena）

- **典型流程**：
  1. `UpdateDefenseAsync` 上传防守阵容
  2. `ListOpponentsAsync` 获取对手
  3. `StartBattleAsync(defenderId, teamJson)` → seed
  4. 演算 → `SettleBattleAsync(..., checksum, replayHash)`
- **服务端**：`arena_service.py`

### 实时房间 PVP — `BaasRoomClient`（pvp）

- **适用**：需要帧同步的实时对战；AFK 卡牌类通常关闭
- **典型流程**：matchmake → start → push_frame / poll_frames → finish
- **服务端**：`room_service.py`

---

## 演示 / 测试专用

| 类 | 说明 |
|----|------|
| `BaasSeedBattleSimulator` | 轻量 seed 演算，用于 E2E 与 Demo，非正式 BattleFoundation |
| `Tests/PlayMode/*` | PlayMode 集成测试 |

---

## 错误处理约定

1. 所有 API 回调 `BaasApiResponse<string>`，`ok=false` 时读 `UserMessage`（中文）
2. 网络层无响应时用 `BaasCoroutineHelper.Fail`
3. 业务码见 `BaasErrorCodes` / `docs/baas_error_codes.md`

---

## maclient 独立演示场景

在 Unity 菜单 **Tools → BaaS → Create All Module Demo Scenes** 一键生成 16 个场景（15 业务模块 + 推图竞技场组合），路径：

`Assets/Content/Scenes/BaasDemos/`

| 场景文件 | 模块 | Host 组件 |
|----------|------|-----------|
| BaasDemo_Login.unity | 账号 | BaasModuleDemoHost |
| BaasDemo_Announce.unity | 公告 | BaasModuleDemoHost |
| BaasDemo_Mail.unity | 邮件 | BaasModuleDemoHost |
| BaasDemo_CloudSave.unity | 云存档 | BaasModuleDemoHost |
| BaasDemo_Leaderboard.unity | 排行榜 | BaasModuleDemoHost |
| BaasDemo_Shop.unity | 商城 | BaasModuleDemoHost |
| BaasDemo_Achievement.unity | 成就 | BaasModuleDemoHost |
| BaasDemo_Gift.unity | 礼包 | BaasModuleDemoHost |
| BaasDemo_Guild.unity | 公会 | BaasModuleDemoHost |
| BaasDemo_BattlePass.unity | 战令 | BaasModuleDemoHost |
| BaasDemo_PeriodicTask.unity | 周期任务 | BaasModuleDemoHost |
| BaasDemo_Compliance.unity | 防沉迷 | BaasModuleDemoHost |
| BaasDemo_Pve.unity | PVE | BaasModuleDemoHost |
| BaasDemo_Arena.unity | 竞技场 | BaasModuleDemoHost |
| BaasDemo_PvpRoom.unity | 实时 PVP | BaasModuleDemoHost |
| BaasCasualBattleDemo.unity | 组合流程 | BaasCasualBattleDemoHost |

Play 前配置 ApiKey 或设置环境变量 `BAAS_E2E_*`；功能未开通时演示会 `[SKIP]` 并写日志。

---

## 接入检查清单

- [ ] `Import-ClientNetworkModule.ps1 -Module baas` 成功
- [ ] `BaasNetworkSettings` 已配置 ApiKey
- [ ] Bootstrap 返回 `feature_flags.pve=true`（若要用 PVE）
- [ ] PlayMode 或 `BaasCasualBattleFlow` 全流程 PASS
