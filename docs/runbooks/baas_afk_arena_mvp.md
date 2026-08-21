# 剑与远征 · 最小可上线包（纯 BaaS）

面向《剑与远征》/《史莱姆大作战》/《冒险大作战》类 **推图 + 养成 + 异步竞技** 游戏，使用 **纯 BaaS（不接 GameServer）** 时的功能清单与 API 对照。

---

## 一、必开 feature（管理台 `feature_flags`）

| 功能键 | 模块 | 上线必要性 |
|--------|------|------------|
| `login` | 账号 | **必开** |
| `mail` | 邮件/补偿 | **必开** |
| `announce` | 公告 | **必开** |
| `economy` | 金币/钻石/商店 | **必开** |
| `pve` | 主线推图 | **必开** |
| `hero` | 英雄背包/升级/装备 | **必开** |
| `gacha` | 抽卡召唤 | **必开** |
| `idle` | 挂机离线收益 | **必开** |
| `arena` | 异步竞技场 | **强烈建议** |
| `tower` | 爬塔/副本变体 | **建议** |
| `leaderboard` | 排行榜 | 建议 |
| `periodic_task` | 日周常 | 建议 |
| `achievement` | 成就 | 可选 |
| `battlepass` | 战令 | 可选 |
| `gift` | 礼包码 | 运营期 |
| `guild` | 公会 | 二期 |
| `iap` | 应用内购 | 付费上线时 |
| `compliance` | 防沉迷 | 国内上线 **必开** |
| `cloudsave` | 通用 KV | **可关**（已有 hero/pve 表） |
| `pvp` | 实时房间 | **关闭**（非此类主玩法） |

### 推荐最小组合（12 项）

```
login, mail, announce, economy, pve, hero, gacha, idle, arena, tower, periodic_task, compliance
```

---

## 二、开箱即用 API 对照（客户端 `BaasFeatureHub`）

| 游戏流程 | Client | 核心 API |
|----------|--------|----------|
| 登录 | `Auth` | `GuestLoginAsync` / `LoginAsync` |
| 公告 | `Announce` | `GetActiveAsync` |
| 邮件 | `Mail` | `GetInboxAsync` → `ClaimMailAsync` |
| 钱包/商店 | `Shop` | `GetWalletAsync` → `GetCatalogAsync` → `PurchaseAsync` |
| **主线推图** | `Pve` | `GetStaminaAsync` → `StartBattleAsync` → `SettleBattleAsync` |
| **英雄养成** | `Hero` | `GetRosterAsync` → `LevelUpAsync` → `EquipAsync` |
| **抽卡** | `Gacha` | `ListPoolsAsync` → `PullAsync` |
| **挂机** | `Idle` | `GetStatusAsync` → `ClaimAsync` |
| **爬塔** | `Tower` | `GetProgressAsync` → `StartBattleAsync` → `SettleBattleAsync` |
| **竞技场** | `Arena` | `UpdateDefenseAsync` → `ListOpponentsAsync` → `StartBattleAsync` → `SettleBattleAsync` |
| 日周常 | `Task` | `ListAsync` → `ReportProgressAsync` → `ClaimAsync` |
| **IAP** | `Iap` | `ListProductsAsync` → `CreateOrderAsync` → `VerifyOrderAsync` |
| 防沉迷 | `Compliance` | `SessionStartAsync` → `HeartbeatAsync` |

REST 前缀：`/api/baas/v1/{service_id}/`

---

## 三、Previously 缺口 → 现已补齐

| 原缺口 | 现模块 | 服务端 | 客户端 |
|--------|--------|--------|--------|
| 抽卡/召唤 | `gacha` | `gacha_service.py` | `BaasGachaClient` |
| 英雄背包/升级/装备 | `hero` | `hero_service.py` | `BaasHeroClient` |
| 挂机离线收益 | `idle` | `idle_service.py` | `BaasIdleClient` |
| 爬塔/副本变体 | `tower` | `tower_service.py` | `BaasTowerClient` |
| 支付 IAP | `iap` | `iap_service.py` | `BaasIapClient` |

数据库迁移：`baas_afk_pack_v1`（`baas_player_heroes`, `baas_gacha_*`, `baas_idle_state`, `baas_tower_progress`, `baas_iap_orders`）

---

## 四、二期补强（已完成）

| 优先级 | 能力 | 状态 | 模块/API |
|--------|------|------|----------|
| P1 | 微信/苹果 IAP 真实验单 | ✅ | `iap_verify.py` + `verify_platform_receipt`；配置 `apple_shared_secret` / `wechat_*` |
| P2 | 独立装备/道具背包 | ✅ | `inventory` feature · `/inventory` · `BaasInventoryClient` · hero.equip 校验背包 |
| P3 | 公会战 / 跨服榜 | ✅ | `/guilds/war/*` · `guild_war:{season}` 榜 · `scope=cross_server` |

上线生产 IAP 时：管理台关闭 `dev_verify_always_ok`，填入平台密钥。

---

## 五、仍可选三期扩展（非阻塞）

| 能力 | 说明 |
|------|------|
| 完整技能 Runtime | 见 `docs/runbooks/skill_framework_evaluation.md` |
| 跨服多实例聚合 | 现跨服榜为单 service 内 guild_war board；多服需网关聚合 |
| IAP 服务端通知回调 | Apple Server Notifications / 微信支付回调 URL |

---

## 六、验证命令

```powershell
cd portals/common/core
py -3 -m pytest tests/test_baas_afk_pack.py tests/test_baas_pve_arena.py -q
py -3 scripts/run_baas_production_readiness_e2e.py --skip-unity
```

maclient 演示场景：`Tools → BaaS → Create All Module Demo Scenes`

---

## 六、典型首日玩家链路（纯 BaaS）

```
Bootstrap → GuestLogin
  → Gacha.Pull（得英雄）
  → Hero.GetRoster / LevelUp
  → Pve.Start → Simulate → Settle（推 1-1）
  → Idle.Claim（离线金币）
  → Tower.Start → Settle（爬塔第 1 层）
  → Arena.UpdateDefense → ListOpponents
  → Shop.GetWallet
  → [付费] Iap.CreateOrder → VerifyOrder
```

以上链路均有独立演示场景与 PlayMode/ pytest 覆盖。
