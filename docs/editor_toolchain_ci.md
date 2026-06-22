# Editor toolchain spike (Wave 4 P2)

## Protocol codegen in CI

1. `portals/common/core/scripts/codegen_protocol_dictionary.py --check`
2. `portals/common/core/scripts/protocol_alignment_ci_gate.py`
3. Jenkins job step (example):

```powershell
cd portals\common\core
py -3 scripts\codegen_protocol_dictionary.py --check
py -3 scripts\protocol_alignment_ci_gate.py
```

## PlayMode evidence archive

After `unity_client_hotupdate_runner` session/smoke/basic:

```powershell
$dest = "docs\evidence\" + (Get-Date -Format yyyy-MM-dd)
New-Item -ItemType Directory -Force -Path $dest
Copy-Item E:\maclient\Library\ClientAcceptance\client-startup-acceptance-report.json $dest\
```

## NET8 gateway spike (P3 pointer)

See `E:\maclient\game-server\docs\platform-roadmap-wave4.md` and evaluate Kestrel WebSocket listener POC in a separate branch.
