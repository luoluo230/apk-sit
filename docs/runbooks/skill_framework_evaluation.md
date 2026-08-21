# 技能框架评估（SkillKit Phase 1–3，BaaS 轻量路径）

> 通用技能模块路径：`maclient/Assets/Modules/SkillKit/`  
> UPM 包名：`com.maclients.skillkit@0.3.0`  
> **AFK / 推图 MVP 不需要 GameServer 帧同步** — 见 [PHASE3.md](../../../maclient/Assets/Modules/SkillKit/PHASE3.md)

## 架构

- **SkillKit.Runtime** — SkillExecutor / TargetSelector / EffectPipeline / BuffSystem / 双 Clock / 弹道 AOI
- **SkillKit.Editor** — SkillAuthoringWindow + Sandbox + Validator + Config 导出
- **BaaS 桥接** — `BaasReplayDigest` / `SkillKitBaasSettlement` → `battle_antifraud.py`
- **集成** — `SkillKitBattleEventAdapter` → BattleEventBus

详见 [SkillKit README](../../../maclient/Assets/Modules/SkillKit/README.md)（maclient 仓库内）。

---

## 现状盘点（maclient）

已有资产：

| 模块 | 状态 | 说明 |
|------|------|------|
| `Skill_Static` / `Skill_Segment` / `Skill_Effect` / `Skill_TargetRule` | ✅ 配置表已存在 | 数据层雏形完整 |
| `BuffRuntime` | ⚠️ 仅数据结构 | 缺统一 Buff 系统 |
| `BattleModel` + `SkillHitEvent` | ⚠️ Demo 级 | 能扣血，无完整技能管线 |
| `SkillTimelinePlayer` | ⚠️ Demo 硬编码 | 未读 Segment 表 |
| `GameMath`（新增） | ✅ 统一数值 | 伤害/范围/挂机/抽卡等 |

**缺口**：配置 → 运行时执行 → 表现时间轴 三层未打通。

---

## 推荐架构（数据 / 表现分离）

```
┌─────────────────────────────────────────────────────────┐
│  Config (Excel/JSON)                                     │
│  Skill_Static · Skill_Segment · Skill_Effect · TargetRule│
└───────────────────────────┬─────────────────────────────┘
                            │
┌───────────────────────────▼─────────────────────────────┐
│  Logic Layer (确定性、可回放、可算 checksum)               │
│  SkillRuntime · BuffSystem · TargetSelector · EffectApplier│
│  使用 GameMath 做伤害/范围/概率                           │
└───────────────────────────┬─────────────────────────────┘
                            │ events (SkillCastStart, Hit, BuffApply...)
┌───────────────────────────▼─────────────────────────────┐
│  View Layer (非确定性、可换皮)                            │
│  SkillTimelinePlayer · VFX/SFX · Anim · DamageText       │
└─────────────────────────────────────────────────────────┘
```

### Logic 层必须支持的能力

| 能力 | 配置字段来源 | 运行时组件 |
|------|-------------|-----------|
| 单段 / 多段 | `Skill_Segment.hit_count`, `hit_interval_ms` | `SegmentScheduler` |
| 前摇 / 引导 | `trigger_timing_type`, `trigger_param` | windup → hit 队列 |
| 指向 / 非指向 | `Skill_TargetRule` | `TargetSelector` |
| 范围（圆/扇/矩） | target rule + GameMath | `GameMath.CanHitTarget` |
| 近战 / 远程 | `cast_type` + range | 射程校验 |
| Buff / Debuff | `Skill_Effect` | `BuffSystem` 叠层/驱散/控制 |
| 控制类 | `BuffFlags.Control` | 行动条/沉默/眩晕 |

### View 层职责

- 只订阅 Logic 事件，**不做伤害结算**
- `SkillTimelinePlayer` 读取 Segment 的 `segment_vfx_id/anim_id/sfx_id`
- 支持跳过/加速（不影响 Logic 结果）

---

## 实施分期建议

### Phase A（MVP，2～3 周）— 建议现在做

1. **`SkillRuntime`**：读 `Skill_Static` + `Skill_Segment`，输出 Hit 事件列表
2. **`BuffSystem`**：回合制 tick、叠层上限、属性修正走 `GameMath`
3. **`TargetSelector`**：单体 / 全体 / 随机 N / 最低血量
4. 打通 `BattleModel.ApplyEvent(SkillHitEvent)`
5. PVE 结算继续用现有 `checksum/replay_hash`

覆盖：剑与远征式 **回合制 / 半自动** 战斗足够。

### Phase B（上线后）— 按需

- 条件触发（HP% / Buff 层数）
- 链式技能 / 被动反击
- 复杂 AOI（多圈、矩形位移）

### Phase C（Realtime PVP 才需要 — **AFK MVP 可跳过**）

- 帧同步 / 状态同步技能锁
- 服务端技能校验或 GameServer 接管

**纯 BaaS AFK 推图不需要 Phase C。** SkillKit Phase 3 已提供客户端弹道 + `replay_hash` 桥接，轻量 BaaS 足够。

---

## 是否「现在全做」？

| 方案 | 优点 | 缺点 |
|------|------|------|
| 全量技能框架 upfront | 一次到位 | 2～3 个月，阻塞 MVP |
| **轻量 Runtime + 表驱动（推荐）** | 与现有表对齐，可渐进 | 极端技能需迭代 |
| 继续 Demo 硬编码 | 快 | 不可维护，无法对齐 BaaS 验签 |

**推荐：Phase A 轻量框架**，不另起一套配置格式，直接复用 `Skill_*` Excel 表。

---

## 与 GameMath 的分工

- **GameMath**：纯函数、无状态、可单元测试、客户端/工具共用
- **SkillRuntime**：有状态、读配置、发事件
- **SkillTimelinePlayer**：只消费事件时间戳

所有伤害、范围、概率公式 **禁止** 在 View 或散落业务里写第二份。

---

## 验收标准（Phase A 完成定义）

- [ ] 至少 3 个技能：单段指向、多段远程、AOE+Buff
- [ ] Buff 可叠加、到期、被驱散
- [ ] 同 seed + team → 同 checksum（与 BaaS PVE 验签一致）
- [ ] 表现层换 VFX 不改 Logic 结果

---

## 相关文件

- 配置：`Assets/Src/HotUpdate/Game/Config/ExcelData/Skill_*.cs`
- 战斗：`Assets/Src/HotUpdate/Game/Battle/`
- 数学：`Assets/Src/HotUpdate/Framework/MathModule/Core/GameMath.cs`
- BaaS 验签：`portals/common/core/services/baas/battle_antifraud.py`
