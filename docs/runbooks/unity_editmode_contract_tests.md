# maclient Unity EditMode 契约测试

Portal 通过 `GET /api/public/unity-contract-manifest` 导出可离线消费的契约清单，maclient 在 EditMode 中按 `unity_editmode_filter` 跑 fixture 断言。

## 拉取 manifest

```bash
curl -s http://127.0.0.1:5003/api/public/unity-contract-manifest -o unity_contract_manifest.json
```

CI 也可直接读取 apk-site 仓库内 `portals/common/core/tests/fixtures/unity_contract_manifest.json`（由 `unity_contract_gate.py` 生成）。

同步到 maclient（Windows）：

```powershell
powershell -ExecutionPolicy Bypass -File scripts\Sync-UnityContractManifest.ps1
powershell -ExecutionPolicy Bypass -File scripts\Sync-UnityContractManifest.ps1 -LocalOnly
```

仅导出到仓库 fixture（跨平台）：

```bash
cd portals/common/core
py -3 scripts/sync_unity_contract_manifest.py --local-only
```

## maclient 侧建议结构

| 测试类 | manifest `unity_editmode_filter` | 断言 |
|--------|----------------------------------|------|
| `BootstrapContractFixtureTests` | topology_bootstrap_v2 | 解析 `fixture.bootstrap` / `network_profile` 与 RuntimeBootstrapService 字段映射 |
| `BaasBootstrapContractFixtureTests` | baas_bootstrap_v1 | BaaS bootstrap 契约 |
| `HotUpdateRegressionFixtureTests` | hotupdate_regression_v1 | catalog / network 对齐键非空且 URL 合法 |

每个 EditMode 测试应：

1. 读取 `Assets/StreamingAssets/unity_contract_manifest.json`（或由 CI 从 Portal 同步）
2. 按 `id` 定位 contract
3. 用 embedded `fixture` 驱动客户端解析逻辑（无需连 Portal）
4. 失败时输出 contract id + 字段路径，便于与 Portal validator 对齐

## Portal 门禁

```bash
cd portals/common/core
py -3 scripts/unity_contract_gate.py
```
