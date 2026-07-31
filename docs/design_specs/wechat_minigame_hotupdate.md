# WeChat minigame hot update (C-P1-3)

## Scope

Platform: `wechat_minigame` — build via Jenkins WxMinigame job; **no HybridCLR** on WebGL/minigame runtime.

## Client path

1. Bootstrap: `GET /api/public/runtime-bootstrap?...&platform=wechat_minigame`
2. Resource delivery: wx backend / CDN URLs from release bundle (not APK)
3. maclient: separate minigame pack CLI (no IL2CPP hotfix DLL path)

## Portal path

- Capability: `platform_capability.py` — `wechat_minigame.can_build=true`
- Scope: four-part `{project}:{env}:{channel}:wechat_minigame`
- Publish: same ReleaseOrder state machine; artifacts = minigame bundle zip

## Verification

```bash
py -3 portals/common/core/scripts/wechat_minigame_publish_e2e.py
```

## Out of scope

HybridCLR on WebGL — use minigame-native update channel only.
