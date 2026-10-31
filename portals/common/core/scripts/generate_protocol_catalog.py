#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Generate protocol-catalog.json for GameServer ClusterProtocolRouteTable."""

from __future__ import annotations

import json
import os
import re
from collections import defaultdict
from pathlib import Path


def main() -> int:
    maclient = Path(os.environ.get("MACLIENT_ROOT") or "E:/maclient")
    server = maclient / "Server"
    ids_cs = (server / "shared/Protocols/Generated/ProtocolIds.cs").read_text(encoding="utf-8")
    meta_cs = (server / "shared/Protocols/ProtocolMetadata.cs").read_text(encoding="utf-8")
    mod_cs = (server / "shared/Protocols/Generated/ProtocolModuleIndex.cs").read_text(encoding="utf-8")

    id_to_name = {
        int(m.group(1)): m.group(2)
        for m in re.finditer(r"\{\s*(\d+)\s*,\s*\"([^\"]+)\"\s*\}", meta_cs)
    }
    proto_to_module: dict[str, str] = {}
    for m in re.finditer(r'\{\s*"([^"]+)"\s*,\s*new\[\]\s*\{\s*([^}]+)\s*\}\s*\}', mod_cs):
        module = m.group(1)
        for p in re.findall(r'"([^"]+)"', m.group(2)):
            proto_to_module[p] = module

    catalog_mods: dict[str, list] = defaultdict(list)
    # Heartbeat is implemented on Game.ProfileBusinessHandler, not Auth.
    auth_force = {10001, 10003, 10005, 10326, 10328, 10330}
    game_force = {10007}

    for m in re.finditer(r"public const int (\w+C2S)\s*=\s*(\d+);", ids_cs):
        family, mid = m.group(1)[:-3], int(m.group(2))
        meta_name = id_to_name.get(mid, family + "_c2s")
        module = proto_to_module.get(family) or "Game"
        if mid in game_force:
            emit_module = "Game"
        elif module == "Auth" or mid in auth_force:
            emit_module = "Auth"
        elif module == "WorldBoss":
            emit_module = "Cross"
        else:
            # Dungeon/PVP match handlers live on Game in multi-console layout.
            emit_module = "Game"
        catalog_mods[emit_module].append(
            {"id": mid, "name": meta_name, "direction": "request"}
        )

    catalog = {
        "generatedFrom": "ProtocolIds+ProtocolModuleIndex",
        "protocols": [
            {"module": mod, "messages": msgs}
            for mod, msgs in sorted(catalog_mods.items())
        ],
    }

    out_paths = [
        server / "protocols/generated/protocol-catalog.json",
        server / "game-server/bin/Debug/protocol-catalog.json",
        maclient / "protocols/generated/protocol-catalog.json",
    ]
    for path in out_paths:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(catalog, ensure_ascii=False, indent=2), encoding="utf-8")
        print(
            f"wrote {path} counts={{{', '.join(f'{k}:{len(v)}' for k,v in sorted(catalog_mods.items()))}}}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
