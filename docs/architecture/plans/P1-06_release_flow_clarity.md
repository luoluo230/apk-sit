# P1-06：发版主线清晰化

| 项 | 值 |
|----|-----|
| 优先级 | P1 |
| 预估 | 4–6 周（分 Step；本轮只做 Step 1） |
| 依赖 | 现有 `release_hub` / `release_console` / `order_state_machine` |
| 参考 | Nexus Release Platform 设计 v1.0（只借模型，不换栈） |
| 状态 | **In Progress**（Step 1–2 已落地，Step 3+ 后续） |

---

## 1. 目标

把「入口多、主键多、计划/线上混在一起」收成一条人话主线：

**线上在跑什么 → 下一步做什么 → 构建出制品 → 组合成 Bundle → 预检 → 审批 → 发布/灰度 → 验证 → 线上生效。**

体验目标：打开发版中心 10 秒内能回答三件事——当前环境客户端加载的是哪个 Bundle、有没有进行中的发版、下一步点哪里。

---

## 2. 范围

**In（Step 1，本轮）**

- 发版中心顶部展示 **线上 Runtime**（active Bundle），而不是模块入口墙
- 用 7 步主线映射现有 order 状态，给出当前步与下一步 CTA
- 侧栏入口改名：发版 / 构建与产物 / 版本与管线 / 发布历史，避免五个「都能发版」
- 晋级区文案改为「同一制品跨环境晋级，不重新构建」

**Out（后续 Step，本轮不做）**

- 换 Java/Vue 或拆微服务
- 新增 CANARY_OBSERVING 等状态枚举（先映射到现有 `published` + 灰度字段）
- Config Center / Agent Lease / HybridCLR 专项预检大改
- 删除 Journey / Console 路由（旧 URL 保留）

---

## 3. 分步实施

### Step 1：主线可见（本轮）

- `services/release/flow_storyline_service.py`
- 发版中心 BFF / 模板 / JS / CSS
- 侧栏文案

**验收**

- [x] Hub API 含 `runtime_snapshot`、`storyline`
- [x] Hub 页可见「线上现状」与 7 步主线
- [x] 侧栏「发版控制台」改为「发版」，「发布单」改为「发布历史」
- [x] 现有 Hub E2E 仍通过

### Step 2：版本页交付线矩阵（本轮）

- 版本页必选环境（无 `env_key` 默认跳转 development）
- 页顶渠道 × 平台矩阵；点格收窄：版本组按环境+平台，VC 按渠道
- 「查看本环境全部」可取消格子过滤
- 侧栏、总览、环境页入口统一为 发版 / 构建与产物 / 版本与管线 / 发布历史
- 去掉发版中心底部「其它入口」墙、版本页隐藏平台页签、旧 `/admin/versions` 全局页（302 到项目列表）
- API：`GET /api/projects/<id>/version-delivery-matrix`

**验收**

- [x] 无 env_key 访问 `/versions` 302 到 `env_key=development`
- [x] 页面含交付线矩阵
- [x] 矩阵 API 返回 cells
- [x] 点格后列表按平台加载版本组、按渠道过滤 VC（前端）

### Step 3：Bundle 硬化（后续）

PROD promote 与 QA 同 `artifact_id + sha256`；BLOCK 非法组合。

### Step 4：灰度观测与回滚基线（后续）

批次 metrics 快照；创建 Release 必选 rollback baseline。

---

## 4. 测试与门禁

- `python -m py_compile` 变更 Python
- `node --check` 变更 JS
- `python -m pytest portals/common/core/tests/test_release_hub.py portals/common/core/tests/test_flow_storyline.py portals/common/core/tests/test_version_delivery_matrix.py portals/common/core/tests/test_delivery_scope.py`
- `python -m pytest portals/common/core/tests/e2e/test_release_hub_e2e.py`

---

## 5. 完成定义（DoD）

- [x] Step 1 验收全部 PASS
- [x] 用户打开发版中心能区分「线上版本」与「进行中发版」
- [x] 未把 PDF 全量页面搬进来
- [x] Step 2 版本页交付线矩阵验收全部 PASS
