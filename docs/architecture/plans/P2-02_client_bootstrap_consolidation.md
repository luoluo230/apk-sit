# P2-02：客户端 Bootstrap 单路径收敛

| 项 | 值 |
|----|-----|
| 优先级 | P2 |
| 预估 | 3–4 周 |
| 依赖 | P0-01（bootstrap API 稳定）, Web runtime-bootstrap 权威 |
| 评审项 | C-P1-1, C-P1-2, C-P1-4 |
| 状态 | **In progress**（Step 1–4 MVP，2026-07-29） |

---

## 1. 目标

**运行时**仅保留 `runtime-bootstrap` 一条路径；`version-resolve` 与 OSS `version_metadata.json` 降级为 **1 个 major 版本的兼容层**后删除。配置烘焙收敛到 Jenkins + 单一 dev asset 模板。

**仓库**：`E:\maclient` + apk-site 契约测试

---

## 2. 范围

**In**

- `Main.cs` 启动链简化
- `HotUpdateConfig` / `ProtocolNetworkSettings` dev 默认值与 Portal 对齐
- 废弃开关 `PreferWebVersionResolve`（改为 bootstrap-only）
- iOS 生产签名（XcodeArchiveCli export plist 完善）— 子项可独立 PR

**Out**

- WebGL 小游戏热更策略（单独 spec）
- 旧客户端 APK 强制升级（产品决策）

---

## 3. 分步实施

### Step 1：Bootstrap 契约门禁（3 天）

**动作**

1. apk-site：`tests/e2e/test_bootstrap_contract.py` 扩展字段断言（network_profile, rollout, force_update）
2. maclient：`Assets/Editor/Tests/BootstrapContractTests.cs` — 解析 sample JSON
3. CI：两端 contract 同一 fixture 文件（submodule 或 copied json）

**验收**

- [x] 字段漂移 CI fail（`bootstrap_contract.py` + 双端 fixture）

---

### Step 2：Main.cs 路径收敛（1 周）

**动作**

1. 启动顺序固定：
   - Try Unified Bootstrap
   - 失败 → 明确错误 UI（**不再** silent fallback OSS）
2. `#if DEVELOPMENT` 可选保留 version-resolve 一次 retry
3. 删除或 `[Obsolete]` `ShouldPreferWebVersionResolve` 生产路径

**改文件**

- `Assets/Src/Main.cs`
- `Assets/Src/HotUpdate/Framework/Bootstrap/RuntimeBootstrapService.cs`

**验收**

- [x] 生产 build 无 silent OSS fallback（`#if DEVELOPMENT` 隔离 legacy）
- [ ] Editor Play + 真机：Portal 关 bootstrap → 失败提示可读
- [ ] Portal 正常 → 仅 1 次 HTTP bootstrap

---

### Step 3：配置烘焙单一入口（4 天）

**动作**

1. 文档化：**唯一写 HotUpdateConfig 的 CI 路径** = `HotUpdateConfigSyncCli` + `Sync-DevStackClientConfig.ps1`
2. 禁止手工改 `.asset` 提交（pre-commit 或 CODEOWNERS）
3. `ProtocolNetworkSettings` 仅 dev 默认 ws://127.0.0.1:15050；其余来自 bootstrap inject

**验收**

- [x] 文档化唯一 CI 入口（`docs/client_bootstrap_contract.md` v2）
- [ ] Jenkins 构建后 asset 与 Portal project 一致（checksum 对比脚本）

---

### Step 4：version-resolve 兼容层标记废弃（3 天）

**动作**

1. apk-site：`version-resolve` 响应 Header `Deprecation: true`, Link bootstrap ✅
2. maclient：生产路径移除 resolve/OSS（Step 2）✅
3. 保留 1 release 后删 API（changelog）⏸

---

### Step 5：iOS 生产签名（1 周，可并行）

**动作**

1. `XcodeArchiveCli.cs` 支持 `ExportOptions.plist` app-store / ad-hoc
2. Web `version_groups[].ios_signing` API 已有 → 管线传入
3. TestFlight upload 与 P0-01 secret 联动

**验收**

- [ ] macOS Jenkins iOS job 产出 ipa + upload（manual）

---

## 4. 完成定义（DoD）

- [x] 生产 build `Main.cs` 无 OSS fallback 路径（release 编译）
- [x] `docs/client_bootstrap_contract.md` 更新为 v2
- [ ] C-P1-1 / C-P1-2 关闭；C-P1-4 有 iOS runbook 或 explicit backlog issue
