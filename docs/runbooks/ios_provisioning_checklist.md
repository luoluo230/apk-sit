# iOS 构建资源 Provisioning Checklist

> 关闭前置：GAP-P2-02-E2E-01、C-P1-4  
> **当前状态：全部未勾 — Wave 4B 硬阻塞**

## 硬件与 Jenkins

- [ ] macOS 构建机（Apple Silicon 或 Intel，Xcode 最新稳定版）
- [ ] Jenkins macOS agent 在线，label 含 `macos` / `ios`
- [ ] Jenkins job 可调用 `jenkins-clone/scripts/commercial_ios_pipeline.sh`

## Apple Developer

- [ ] Apple Developer Program 账号有效
- [ ] App ID / Bundle ID 与 Portal `ios_signing.bundle_id` 一致
- [ ] Distribution 证书 + `.p12` 导入 Jenkins Credentials
- [ ] Provisioning Profile（App Store / Ad Hoc）导入 Jenkins
- [ ] App Store Connect API Key（TestFlight upload）

## Portal 配置

- [ ] Version Group → iOS Signing wizard 校验通过
- [ ] `IOS_SIGNING_JSON` 注入 Jenkins 参数
- [ ] `docs/runbooks/ios_production_signing.md` 步骤可在 staging 复现

## E2E 验收（全部勾选后才可 closure）

- [ ] macOS Jenkins build 产出 `.ipa`
- [ ] TestFlight upload 成功（ASC 日志）
- [ ] evidence：`docs/evidence/YYYY-MM-DD/GAP-P2-02-E2E-01.json`

## 阻塞说明

无 macOS 资源时 Master gate 对 iOS GAP 报 `BLOCKED`（预期行为，非降级）。
