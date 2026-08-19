# BaaS 客户端快速接入指南

面向新 Unity 项目：从零到可调通 PVE / 竞技场 / 邮件等业务的完整步骤。

## 1. 服务端准备

1. Portal 项目设置 `server_mode = casual_baas`
2. 创建休闲 BaaS 服务，记录 **GameId / GameKey / Service API Key**
3. 在管理台勾选需要的功能（PVE、竞技场、邮件等）
4. 本地启动：`powershell -File scripts/Start-BaaSStack.ps1 -Background -Port 5004`

## 2. 导入客户端模块

```powershell
# 在 apk-site 根目录
powershell -ExecutionPolicy Bypass -File scripts/Export-ClientNetworkModule.ps1 -Module baas
powershell -ExecutionPolicy Bypass -File scripts/Import-ClientNetworkModule.ps1 -Module baas -MaclientRoot E:\maclient
```

导入后 maclient 出现：
- `Assets/Modules/BaasNetwork/` — 全部 Runtime 与 PlayMode 测试
- `Assets/Src/HotUpdate/Framework/Network/Abstractions/` — 模块探测桩

HotUpdate 程序集需引用 `MAClient.Network.Baas`（asmdef GUID `44a166a60ef4acf4fae258dc99b5e64e`）。

## 3. 配置 ScriptableObject

创建 `Resources/Protocol/BaasNetworkSettings.asset`：

| 字段 | 说明 |
|------|------|
| PortalBaseUrl | 如 `http://127.0.0.1:5004` |
| GameId / GameKey | 项目凭证 |
| ApiKey | 服务 API 密钥（bootstrap 不会下发） |
| AutoGuestLoginAfterBootstrap | 是否自动游客登录 |

## 4. 最小代码（Bootstrap → 调 API）

```csharp
using System.Collections;
using MAClient.Network.Baas;
using UnityEngine;

public class BaasQuickStart : MonoBehaviour
{
    IEnumerator Start()
    {
        var settings = BaasNetworkSettings.LoadOrDefault();
        var bootstrap = new BaasBootstrapService(settings);
        bool ok = false;
        string err = null;
        yield return bootstrap.BootstrapCoroutine((success, error) => { ok = success; err = error; });
        if (!ok) { Debug.LogError(err); yield break; }

        var hub = new BaasFeatureHub(bootstrap.Context);

        // 示例：查 PVE 体力（需管理台开启 pve）
        if (hub.IsEnabled(BaasFeatureKeys.Pve))
        {
            BaasApiResponse<string> stamina = null;
            yield return BaasCoroutineHelper.Invoke(
                cb => hub.Pve.GetStaminaAsync(cb),
                r => stamina = r);
            Debug.Log(stamina.ok ? stamina.data : stamina.UserMessage);
        }
    }
}
```

## 5. 业务模块一览

详见 `packages/client_network/baas/MODULES.zh-CN.md`。

核心类：

| 类 | 职责 |
|----|------|
| `BaasBootstrapService` | Bootstrap + 可选游客登录 |
| `BaasFeatureHub` | 各业务 Client 统一入口（含功能门控） |
| `BaasFeatureKeys` | 功能开关键常量 |
| `BaasCoroutineHelper` | 协程 API 统一错误处理 |
| `BaasApiResponse<T>` | 响应封装 + 中文错误信息 |
| `BaasPveClient` / `BaasArenaClient` | 战斗类（含 checksum / replay_hash） |

## 6. PVE + 竞技场典型流程

```
Bootstrap → GuestLogin
  → hub.Pve.GetStamina
  → hub.Pve.StartBattle(stage, team) → seed
  → BaasSeedBattleSimulator.SimulatePve(seed, heroes)
  → hub.Pve.SettleBattle(..., checksum, replay_hash)
  → hub.Arena.UpdateDefense / ListOpponents / StartBattle / SettleBattle
```

完整演示：`maclient/Assets/Src/HotUpdate/Game/Network/Baas/BaasCasualBattleFlow.cs`

## 7. 验证

```powershell
# 服务端
cd portals/common/core
py -3 -m pytest tests/test_baas_pve_arena.py -q

# Unity PlayMode
py -3 scripts/run_baas_playmode_e2e.py

# 生产就绪全栈
py -3 scripts/run_baas_production_readiness_e2e.py
```

## 8. 环境变量（CI / E2E）

| 变量 | 用途 |
|------|------|
| BAAS_E2E_PORTAL | Portal 地址 |
| BAAS_E2E_GAME_ID / GAME_KEY / API_KEY | 项目凭证 |
| BAAS_E2E_SERVICE_ID | 指定服务 UUID |

## 注意

- 同一 Unity 工程不要同时导入 topology + baas，除非明确双栈
- 未开通的功能访问 `BaasFeatureHub` 对应属性会抛异常，请先用 `IsEnabled()` 判断
- 战斗结算必须与服务端 `anti_cheat` 配置一致（checksum + replay_hash）
