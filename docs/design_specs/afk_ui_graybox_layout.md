# AFK 全套 UI 灰盒布局规范（美术交接版）

> **版本** v1.2 · **基准分辨率** 1536×2730 竖屏 · **引擎** Unity uGUI  
> **程序入口** `E:/maclient/Assets/Src/HotUpdate/Game/Afk/UI/`  
> **设计令牌** `AfkUITheme.cs` · **美术位** `AfkUIArtSlot.cs` · **字体** `AfkUIFontCatalog.cs`  
> **Framework 接入** `AfkUIFrameworkBootstrap.cs` · `AfkUIFeedbackService.cs`

---

## 1. 文档用途

| 读者 | 用途 |
|------|------|
| **美术** | 按 ArtSlot 名与尺寸出图；按色板/字号替换灰盒 |
| **策划** | 核对信息架构、Tab 与子页流程 |
| **程序** | 布局尺寸与节点命名对齐；Push 子页与主 Tab 壳层分离 |

**参考截图（程序灰盒 v1.1 前）** — 存放于 `docs/design_assets/afk/`：

| 文件 | 内容 |
|------|------|
| `graybox_home_reference.png` | 主页 Tab |
| `graybox_hero_list_reference.png` | 英雄 Tab |
| `graybox_battle_console_reference.png` | 战斗 Console（非 UI 模块） |

> v1.1 起子页改为 **全屏 Push**（保留顶栏/底栏），英雄详情在 Push 内全宽滚动，不再使用居中 Sheet 弹窗。

---

## 2. 壳层结构（固定）

```
┌──────────────────────────────────────┐  ← TopBar 168h
│ 💰 金币/钻石    战力        通关进度   │
├──────────────────────────────────────┤
│                                      │
│         Scroll Content Area          │  ← 可滚动主内容 / Push 子页
│         (padding 32 L/R)             │
│                                      │
├──────────────────────────────────────┤  ← BottomNav 168h
│ 主页 │ 英雄 │ 冒险 │ 副本 │ 更多      │
└──────────────────────────────────────┘
```

| 区域 | 高度 | 背景色 token | 说明 |
|------|------|--------------|------|
| TopBar | **168** | `Panel` #242838 | 资源、战力、关卡进度；品牌字「AFK · 剑与远征」 |
| Content | 2730−168−168 = **2394** | `BgDark` #141923 | VerticalLayout spacing **14** |
| BottomNav | **168** | `Panel` | 5 Tab；选中 `TabActive` + 底部 4px `Gold` 指示条 |
| Push 子页 | 同 Content 区 | `BgMid` #1C2130 | PushHeader **112** + 滚动区 |

**内容区安全边距：** 左右 `ContentPadH` = **32**，区块间距 `SectionGap` = **20**。

---

## 3. 设计令牌

### 3.1 色板（与 `AfkUITheme.cs` 同步）

| Token | Hex | 用途 |
|-------|-----|------|
| BgDark | #141923 | 页面底 |
| BgMid | #1C2130 | Push 子页底 |
| Panel | #242838 | 卡片、顶/底栏 |
| PanelLight | #30384D | 次级按钮、Action 卡片 |
| PanelStroke | #47536B @55% | 描边 |
| Gold | #F5C748 | 标题、章节、Tab 指示 |
| Diamond | #73C7FF | 战力、钻石 |
| Accent | #945BD1 | 主色、Tab 选中、Action 底条 |
| AccentWarm | #EB8538 | 主 CTA、领取、挑战 |
| Success | #4DC778 | 升级、可领取 |
| Danger | #E84D3D | 警示 |
| TextPrimary | #F5F7FC | 正文 |
| TextMuted | #9EA8C2 | 辅助说明 |
| ArtSlotFill | #2E3648 | 美术占位底 |
| ArtSlotBorder | #738099 @85% | 美术占位描边 |
| ArtSlotLabel | #8B96AD | 占位标注字 |

### 3.2 字号（LegacyRuntime @1536 宽）

| Token | px | 用途 |
|-------|-----|------|
| HeroFont | 48 | 英雄详情名 |
| TitleFont | 40 | Section 标题 |
| SubtitleFont | 30 | 卡片标题、KPI 数值 |
| BodyFont | 28 | 正文、按钮 |
| SmallFont | 24 | 顶栏副信息 |
| CaptionFont | 22 | 辅助、ArtSlot 标注 |

### 3.3 间距与圆角

| Token | 值 | 说明 |
|-------|-----|------|
| RowGap | 14 | 列表行间距 |
| SectionGap | 20 | 区块间距 |
| ContentPadH | 32 | 内容左右 padding |
| Outline | 1.5px | 卡片描边（Outline 组件） |
| ActionCard accent | 4h | 卡片底部强调条，非大块色带 |

---

## 4. 信息架构

### 4.1 底部 Tab

| Tab ID | 文案 | 职责 |
|--------|------|------|
| home | 主页 | 摘要、挂机、活动、Banner、CTA、快捷、核心玩法 |
| hero | 英雄 | KPI + 列表（按战力）→ Push 详情 |
| adventure | 冒险 | 阵容条 + 章节关卡 |
| dungeon | 副本 | 单人本 + 爬塔 + 组队 |
| more | 更多 | 系统中心 Hub |

### 4.2 子页（Push + ← 返回）

顶栏/底栏 **保留**；内容区 **全屏 Push**，PushHeader 含「← 返回」+ 标题 + 副标题。

| 子页 | 标题 | 副标题 |
|------|------|--------|
| 布阵 | 布阵 | 5 人阵容 · 点击槽位选人 |
| 英雄详情 | 英雄详情 | 属性 / 技能 / 装备 |
| 关卡地图 | 关卡地图 | 章节路线 · 选择关卡挑战 |
| 召唤 | 召唤 | 消耗钻石抽取英雄 |
| 商店 | 商店 | 多币种兑换 · 分类浏览 |
| 邮件 | 邮件 | 系统与奖励邮件 |
| 任务 | 任务 | 每日 / 每周目标 |
| … | 见 `AfkMainPanel.SubPageSubtitle` | |

### 4.3 留存子页内 Tab

| 页面 | Tab 标签 |
|------|----------|
| 商店 | 全部 / 金币 / 钻石 / 公会 / 竞技 |
| 邮件 | 全部 / 可领取 / 已领取 |
| 任务 | 全部 / 每日 / 每周 |
| VIP | 特权 / 充值 / 每日 |

---

## 5. 页面线框

### 5.1 主页（home）— 自上而下

| # | 节点名 | 高度 | 说明 |
|---|--------|------|------|
| 1 | `ArtSlot_PlayerSummary` | 168 | 头像 112 + 名/VIP/战力/进度 |
| 2 | `ArtSlot_IdleWidget` | 200 | 挂机图标 120 + 进度条 + 「领取」 |
| 3 | `ArtSlot_EventBanner` ×3 | 180 | 活动横条，可点击 |
| 4 | `ArtSlot_Banner` | **520** | 主视觉 KV，底部 caption 条 |
| 5 | `PrimaryCTA` | 112 | 挑战下一关，暖色大按钮 |
| 6 | `ShortcutStrip` | 104 | 邮件/任务/商店/战令，图标 40×40 |
| 7 | Section「核心玩法」 | — | 左金条 4px + 标题 |
| 8 | `ActionGrid` ×2 | 128×2+14 | 2 列 × 2 行，底 Accent 4px |

### 5.2 英雄（hero）

| 区块 | 组件 | 说明 |
|------|------|------|
| KPI | `KpiRow` 96h ×3 | 英雄数 / 平均战力 / 最高星级 |
| 列表 | `HeroCard` 176h | `ArtSlot_Portrait` 128 + 名/级/星/战力 + 详情/升级/升星 |
| 详情 | Push 全屏 | `ArtSlot_HeroDetailPortrait` 240 + 属性/技能/装备 |

### 5.3 冒险（adventure）

- `KpiRow`：当前章 / 下一关 / 战力  
- `FormationBar` 160h：5 槽 88×88 + 自动布阵  
- `PrimaryCTA`：打开关卡地图  
- `StageRow` 108h ×10：锁定态灰化 + 挑战 tag  

### 5.4 副本（dungeon）

- 单人本：`AddDungeonCard` + `ArtSlot_DungeonThumb` 120×120  
- 爬塔：`ArtSlot_TowerBanner` 全宽×140  
- 组队本：同上卡片样式  

### 5.5 更多（more）

分 **HubSection**（Section 标题 + ActionGrid + 16 间距）：

1. 日常 — 邮件、任务、成就、战令  
2. 对战/排行 — 竞技、赛季、排行榜、好友  
3. 社交/公会 — 公会、好友、爬塔、天赋  
4. 商业化 — 商店、VIP、礼包、召唤  
5. 装备深度 — 强化、精炼、觉醒、英雄列表  

---

## 6. ArtSlot 交付清单

程序侧所有占位节点均命名为 `ArtSlot_*`，灰盒显示 **slot 名 + 建议尺寸**。

| Slot 名 | 建议尺寸 (px) | 格式 | 用途 |
|---------|---------------|------|------|
| ArtSlot_Avatar | 112×112 | PNG | 玩家头像 |
| ArtSlot_Banner | 1472×520 | PNG/JPG | 主页 KV（全宽−64 padding） |
| ArtSlot_Portrait | 128×128 | PNG | 英雄列表头像 |
| ArtSlot_HeroDetailPortrait | 240×240 | PNG | 英雄详情立绘 |
| ArtSlot_DungeonThumb | 120×120 | PNG | 副本缩略图 |
| ArtSlot_TowerBanner | 1472×140 | PNG | 爬塔头图 |
| ArtSlot_SeasonBanner | 1472×140 | PNG | 赛季头图 |
| ArtSlot_GuildBanner | 1472×140 | PNG | 公会头图 |
| ArtSlot_VipBadge | 96×96 | PNG | VIP 徽章 |
| ArtSlot_TierBadge | 72×72 | PNG | 段位图标 |
| ArtSlot_EventBanner | flex×180 | PNG | 活动条（约 480×180/卡） |
| ArtSlot_IdleIcon | 120×120 | PNG | 挂机图标 |
| ArtSlot_ShortcutIcon | 40×40 | PNG | 快捷入口图标 ×4 |
| ArtSlot_SkillIcon | 64×64 | PNG | 技能图标 |
| ArtSlot_FormationStage | 1472×360 | PNG | 布阵舞台底图 |
| ArtSlot_FormSlot_{1-5} | flex×168 | PNG | 阵位框 |

**替换方式：** 在 Prefab / 运行时节点上保留同名 RectTransform，替换 `Image.sprite` 即可；程序通过 `AfkUIArtSlot` 统一底色，美术接入后可隐藏 `ArtSlot_Label` 子节点。

---

## 7. 组件清单（程序已实现）

| 组件 | 文件 | 典型高度 |
|------|------|----------|
| TabBar | AfkUILayoutComponents | 72 |
| KpiRow | 同上 | 96 |
| InfoCard | 同上 | 140 |
| ProgressBar | 同上 | 64 |
| InputRow | 同上 | 88 |
| ChipGroup | 同上 | 56 |
| ProductCard / MailCard / OpponentCard | 同上 | 112–136 |
| TierLadderRow / RankRow | 同上 | 80–120 |
| EmptyState | 同上 | 220 |
| HubSection | 同上 | Section+Grid |
| PlayerSummary / IdleWidget / EventCarousel | 同上 | 见 §5 |
| Push 子页壳 | AfkUiFeedback | PushHeader 112 |

---

## 8. 交互与反馈

| 交互 | 反馈 |
|------|------|
| 主按钮 / 卡片点击 | 按钮 ColorTint + 跳转 Push 或战斗 |
| 领取 / 升级 / 升星 | 顶部 Toast 2.2s（成功绿 / 失败红） |
| Tab 切换 | 背景色 + 底部金条 + 列表重建 |
| Push 返回 | 关闭 Push，回到 Tab 列表 |
| 红点 | 28×28 圆点，键名见 `AfkRedDotKeys` |

---

## 9. 美术对接流程

1. **策划确认** 本文档 §4 信息架构无遗漏。  
2. **美术按 §6 出图**，命名与 Slot 名一致，@2x 基于 1536 宽。  
3. **程序/美术在 Unity Prefab** `Resources/UI/AfkMainPanel.prefab` 或运行时节点上换图。  
4. **回归** §10 验收清单 + Play Mode 跑通 BaaS 联机流程。

**生成/刷新 Prefab：** Unity 菜单 `Tools → AfkGame → Generate UI Prefabs (Bundle Ready)`

---

## 10. 验收清单

### 布局

- [ ] 5 Tab 切换无错位；Scroll 不被 TopBar/BottomNav 遮挡  
- [ ] 主页区块顺序与 §5.1 一致；Banner 520h、Event 180h  
- [ ] 所有 ArtSlot 可见 slot 名 + 尺寸标注  
- [ ] 子页为 Push 全屏（非居中弹窗）；← 返回可用  
- [ ] Section 标题左侧 4px 紫条 + 金色 TitleFont  

### 流程

- [ ] 主页 → Shortcut / ActionGrid → Push 子页 → 返回  
- [ ] 英雄列表 → 详情 Push → 升级/升星 Toast  
- [ ] 商店/邮件/任务/VIP 内 Tab 筛选有效  
- [ ] 礼包输入、好友/公会输入可提交  
- [ ] BaaS 联机后留存页数据刷新  

### 视觉（美术接棒前灰盒）

- [ ] 色板与 §3.1 一致（可在 Play Mode 取样验证）  
- [ ] 无大块纯色「假按钮」遮挡 ArtSlot 标注  
- [ ] Action 卡片仅 4px 底条强调，非整行色带  

---

## 11. 代码索引

| 模块 | 路径 |
|------|------|
| 主壳 | `UI/Prefab/AfkMainPanel.cs` |
| 主题 | `UI/AfkUITheme.cs` |
| 美术位 | `UI/AfkUIArtSlot.cs` |
| 布局工厂 | `UI/AfkUILayoutFactory.cs` + `AfkUILayoutComponents.cs` + `AfkUILayoutScreens.cs` |
| 留存页 | `UI/AfkRetentionUILayout.cs` |
| Push/Toast/Modal | `AfkUIFeedbackService.cs` + `AfkToastPanel` / `AfkModalPanel` / `AfkSubPagePanel` |
| Framework 引导 | `AfkGuideOrchestrator.cs` + `UIGuideService` |
| App 入服模块 | `Game/Afk/AfkInGameModule.cs` |
| 字体规划 | `AfkUIFontCatalog.cs` |
| Prefab 生成 | `Assets/Editor/AfkGame/AfkUIPrefabGenerator.cs` |

---

## 13. 字体与排版规划

| 角色 Role | 字号 token | 默认字体 | 默认色 | 用途 |
|-----------|------------|----------|--------|------|
| Display | HeroFont 48 | AfkUI_Display* | Gold | 英雄详情名 |
| Title | TitleFont 40 | AfkUI_Main* | Gold | Section 标题 |
| Subtitle | SubtitleFont 30 | AfkUI_Main | TextPrimary | 卡片标题、Push 页眉 |
| Body | BodyFont 28 | AfkUI_Main | TextPrimary | 正文、按钮 |
| Small | SmallFont 24 | AfkUI_Main | TextMuted | 顶栏副信息 |
| Caption | CaptionFont 22 | AfkUI_Main | TextMuted | 辅助、ArtSlot 标注 |
| Numeric | SubtitleFont 30 | AfkUI_Main | Diamond | 战力、货币数字 |

\* 美术交付路径：`Resources/Fonts/AfkUI_Main.ttf`（正文）、`Resources/Fonts/AfkUI_Display.ttf`（大标题，可选）。未交付前程序使用 `LegacyRuntime.ttf` 占位。

**程序用法：** `AfkUIFontCatalog.Apply(text, Role)` 或 `AfkUIBuilder.AddText(rt, text, Role)`。

---

## 14. 弹窗 / 提示分层（Framework 实现）

AFK 模块 **必须** 走 HotUpdate Framework，禁止在业务里自建 MonoBehaviour 弹层。

| 层级 | 类型 | Framework 组件 | 触发 API |
|------|------|----------------|----------|
| L1 | **Toast 提示** | `AfkToastPanel` + `NotificationCenter` | `AfkUIFeedbackService.ShowToast(msg, success)` |
| L2 | **Push 子页** | `AfkSubPagePanel`（全屏，保留顶/底栏） | `OpenSubPage` / 主页 Shortcut、英雄详情 |
| L3 | **Modal 确认** | `AfkModalPanel`（`UIManager` 弹窗队列） | `AfkUIFeedbackService.Confirm(...)` |
| L4 | **战斗结算** | `AfkBattleOverlayPanel` : `UIPanelBase` | 战斗结束流程 |

**主题常量：** `AfkUITopics.Toast` / `Refresh` / `ModalRequest` 等。

**定时隐藏：** Toast 使用 `PresentationRuntimeContext.TimerManager`（非手写 Coroutine）。

**音效（可选）：** `AudioManager.PlaySfx2D("ui_click"|"ui_toast_success", busType: Ui)`。

---

## 15. Framework 接入清单（AFK 试玩 = 框架验收）

| 能力 | Framework 类 | AFK 接入状态 |
|------|--------------|--------------|
| UI 路由/面板 | `UIManager` + `UIRouteDefinition` | `afk/main` 路由；`NavigateToRoute` 打开主面板 |
| 热更 UI | `UIHotUpdateResourceBootstrap` | Bootstrap 内 `ConfigureForCurrentRuntime` |
| 红点 | `UIRedDotService` | `AfkRedDotSystem` |
| 通知 | `INotificationCenter` | Toast / Refresh |
| 全局事件 | `EventManager` | `AfkUITopics.Refresh` |
| 定时器 | `TimerManager` | Toast 自动隐藏 |
| 音效 | `AudioManager` | UI 点击 / Toast |
| 特效 | `PresentationFacade` | 战斗层 `AfkBattlePresentation` |
| 战斗事件 | `BattleEventBus` | SkillKit 战斗 |
| 战斗状态机 | `BattleStateMachine` | `BattleController` |
| App 状态机 | `GameState.StateMachine` | `AfkInGameModule` + `InGameState.OnEnter` → `BootstrapFromAppEntry`；独立场景仍可用 `AfkGamePlayHost.AutoLoadOnAwake` |
| 新手引导 | `UIGuideService` | `AfkGuideOrchestrator` Block/Release Tab 路由 `afk/tab/{id}` |
| Presenter | `UIPresenterBase<T>` | `AfkMainPanelPresenter` |
| 战斗表现 | `BattlePresentationService` | **分析完成**，见 `afk_battle_presentation_framework_analysis.md`；Phase 0 待实现 |

**启动顺序（对齐 LoginModule）：**

1. **完整 App：** `Boot → Startup → LoginState → InGameState` → `AfkInGameModule.EnsureRuntime` → `BootstrapFromAppEntry`  
2. **AFK 独立场景：** `AfkGamePlayHost.Awake` → `Bootstrap`（含 AFK 登录面板）  
3. `AfkUIFrameworkBootstrap.Ensure(host, transform)`  
4. `UIManager.NavigateToRoute("afk/main")`  
5. `AfkUIFeedbackService` 初始化 Toast 常驻面板  
6. 首次进入：`AfkGuideOrchestrator.Begin` → `UIGuideService.Block` 限制 Tab

---

## 12. 变更记录

| 版本 | 日期 | 说明 |
|------|------|------|
| v1.0 | 2026-07 | 初版灰盒 IA + 组件清单 |
| v1.1 | 2026-07-24 | 正式美术交接：Push 子页、ArtSlot 统一标注、色板 hex、Section 金条、Action 4px 底条、参考截图归档 |
| v1.2 | 2026-07-24 | Framework 接入：字体规划、Toast/Modal/SubPage 分层、UIManager 路由、TimerManager/NotificationCenter |
| v1.3 | 2026-07-24 | App FSM：`AfkInGameModule`；新手引导 `UIGuideService`；战斗表现 Framework 分析文档 |
