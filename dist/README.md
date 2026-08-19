# Release artifacts（发布产物）

生成时间戳：`20260819_174805`（可用脚本重新生成）

## 服务器部署包

| 文件 | 说明 |
|------|------|
| `topology-server-architecture.zip` | 中重度拓扑服务器架构（合并到 apk-site 根目录） |
| `baas-server-architecture.zip` | 轻度 Casual BaaS 独立服务器架构 |

包内必读：

- 拓扑：`docs/runbooks/topology_server_deploy_step_by_step.md`
- BaaS：`docs/runbooks/baas_server_deploy_step_by_step.md`

## 客户端网络模块（按需导入 Unity）

| 文件 | 配对服务端 | 导入目标 |
|------|------------|----------|
| `client-network-topology.zip` | `topology_server` | `Assets/Modules/TopologyNetwork` |
| `client-network-baas.zip` | `casual_baas_server` | `Assets/Modules/BaasNetwork` |

每个客户端 ZIP 内含 `README_IMPORT.md` 与 `SERVER_DEPLOY_GUIDE.md`。

## 重新生成

```powershell
cd E:\web\apk-site
powershell -ExecutionPolicy Bypass -File scripts\Build-AllReleaseArtifacts.ps1 -MaclientRoot E:\maclient
```

## maclient 基线

执行 `scripts\Remove-ClientNetworkModuleResidual.ps1` 后，Unity 工程仅保留 `ClientNetworkModuleGate`（Abstractions），不含已导入模块代码。
