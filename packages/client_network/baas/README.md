# BaaS Client Network Module

轻量级休闲游戏 **客户端网络模块**，与 Portal `casual_baas_server` 配对使用。

> 中文模块说明见 [MODULES.zh-CN.md](./MODULES.zh-CN.md)  
> 接入步骤见 [docs/runbooks/baas_client_onboarding.md](../../docs/runbooks/baas_client_onboarding.md)

## Export / Import

```powershell
powershell -ExecutionPolicy Bypass -File scripts/Export-ClientNetworkModule.ps1 -Module baas
powershell -ExecutionPolicy Bypass -File scripts/Import-ClientNetworkModule.ps1 -Module baas -MaclientRoot E:\maclient
```

Base project only needs `ClientNetworkModuleGate` (stubs). Do not import topology in the same product unless dual-stack.

## Architecture

```
BaasNetworkSettings
    → BaasBootstrapService (INetworkModule)
        → BaasClientContext + FeatureFlags + Endpoints
            → BaasFeatureHub
                → BaasAuthClient / BaasPveClient / BaasArenaClient / …
```

## Runtime API

| Class | Feature key | Purpose |
|-------|-------------|---------|
| `BaasBootstrapService` | — | Bootstrap + optional guest login |
| `BaasFeatureHub` | — | Unified module accessor with feature gating |
| `BaasFeatureKeys` | — | Feature flag constants |
| `BaasCoroutineHelper` | — | Coroutine invoke + error helper |
| `BaasAuthClient` | login | Guest / password auth |
| `BaasAnnounceClient` | announce | Announcements |
| `BaasMailClient` | mail | Inbox + claim |
| `BaasCloudSaveClient` | cloudsave | KV cloud save |
| `BaasLeaderboardClient` | leaderboard | Score boards |
| `BaasShopClient` | economy | Shop + wallet |
| `BaasAchievementClient` | achievement | Achievements |
| `BaasGiftClient` | gift | Gift codes |
| `BaasGuildClient` | guild | Guilds |
| `BaasBattlePassClient` | battlepass | Battle pass |
| `BaasTaskClient` | periodic_task | Daily/weekly tasks |
| `BaasComplianceClient` | compliance | Anti-addiction |
| `BaasPveClient` | pve | AFK-style PVE stages |
| `BaasArenaClient` | arena | Async arena PVP |
| `BaasRoomClient` | pvp | Realtime room PVP |

Namespace: `MAClient.Network.Baas`  
Assembly: `MAClient.Network.Baas.asmdef`

## Quick start

```csharp
var bootstrap = new BaasBootstrapService(BaasNetworkSettings.LoadOrDefault());
yield return bootstrap.BootstrapCoroutine((ok, err) => { /* ... */ });
var hub = new BaasFeatureHub(bootstrap.Context);
yield return hub.Pve.GetStaminaAsync(resp => Debug.Log(resp.UserMessage));
```

## E2E

```powershell
cd portals/common/core
py -3 scripts/run_baas_playmode_e2e.py
py -3 scripts/run_baas_production_readiness_e2e.py
```

Environment: `BAAS_E2E_PORTAL`, `BAAS_E2E_API_KEY`, `BAAS_E2E_GAME_ID`, `BAAS_E2E_GAME_KEY`

## Contract version

Bootstrap returns `contract_version`; client zip includes generated `BaasErrorCodes` / `BaasOpenApiEndpoints` from `scripts/generate_baas_error_artifacts.py`.
