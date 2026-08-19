# BaaS Client Network Module

Pairs with **casual_baas_server** (`PORTAL_SERVER_FRAMEWORKS=baas`).

## Export / Import (decoupled)

```powershell
# From apk-site repo root — export standalone zip
powershell -ExecutionPolicy Bypass -File scripts/Export-ClientNetworkModule.ps1 -Module baas

# Import into maclient (creates Assets/Modules/BaasNetwork)
powershell -ExecutionPolicy Bypass -File scripts/Import-ClientNetworkModule.ps1 -Module baas -MaclientRoot E:\maclient
```

Unity menu (maclient): `Tools/MAClient/协议与网络/导出BaaS网络模块ZIP`

Base project only needs `ClientNetworkModuleGate` (stubs). **Do not** import topology module in the same product unless running dual-stack.

## Runtime API

| Class | Purpose |
|-------|---------|
| `BaasNetworkModule` | client-bootstrap |
| `BaasRoomClient` | guest login, matchmake, start, push_frame, poll_frames, finish |

Namespace: `MAClient.Network.Baas`  
Assembly: `MAClient.Network.Baas.asmdef`

## Live E2E (PlayMode)

```powershell
$env:BAAS_E2E_PORTAL="http://127.0.0.1:5004"
$env:BAAS_E2E_SERVICE_ID="<service-uuid>"
$env:BAAS_E2E_API_KEY="<api-secret>"
# Unity PlayMode: BaasRoomFanoutPlayModeTests
```

## MVP boundary

See `docs/design_specs/casual_baas_pvp_mvp_boundary.md`
