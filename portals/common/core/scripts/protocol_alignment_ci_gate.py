# -*- coding: utf-8 -*-
"""CI gate: protocols.json must align with server ProtocolDictionary.cs (T-B02)."""

from __future__ import annotations

import json
import os
import re
import sys

MACLIENT_ROOT = os.environ.get("MACLIENT_ROOT", r"E:\maclient")
PROTOCOLS_JSON = os.path.join(MACLIENT_ROOT, "Assets", "Src", "Protocols", "protocols.json")
PROTOCOL_DICT = os.path.join(
    MACLIENT_ROOT, "game-server", "shared", "Protocols", "Generated", "ProtocolDictionary.cs"
)


def _load_protocol_ids(path: str) -> dict[str, int]:
    with open(path, encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("protocols.json root must be object")
    out: dict[str, int] = {}
    for name, row in payload.items():
        if not isinstance(row, dict):
            continue
        msg_id = row.get("MessageID")
        if msg_id is None:
            msg_id = row.get("messageId") or row.get("id")
        if msg_id is not None:
            out[str(name)] = int(msg_id)
    return out


def _load_dictionary_ids(path: str) -> dict[str, int]:
    text = open(path, encoding="utf-8").read()
    pattern = re.compile(r'\{\s*"([^"]+)"\s*,\s*(\d+)\s*\}')
    return {name: int(msg_id) for name, msg_id in pattern.findall(text)}


def main() -> int:
    if not os.path.isfile(PROTOCOLS_JSON):
        allow_skip = str(os.environ.get("ALLOW_PROTOCOL_SKIP", "")).lower() in ("1", "true", "yes")
        if allow_skip:
            print(f"SKIP: protocols.json not found: {PROTOCOLS_JSON}")
            return 0
        print(f"FAIL: protocols.json not found: {PROTOCOLS_JSON}", file=sys.stderr)
        return 1
    if not os.path.isfile(PROTOCOL_DICT):
        print(f"FAIL: ProtocolDictionary missing: {PROTOCOL_DICT}")
        return 1

    client = _load_protocol_ids(PROTOCOLS_JSON)
    server = _load_dictionary_ids(PROTOCOL_DICT)
    missing_on_server = sorted(set(client) - set(server))
    missing_on_client = sorted(set(server) - set(client))
    mismatched = sorted(
        name for name in client.keys() & server.keys() if client[name] != server[name]
    )
    if missing_on_server or missing_on_client or mismatched:
        print(json.dumps({
            "ok": False,
            "client_count": len(client),
            "server_count": len(server),
            "missing_on_server": missing_on_server[:20],
            "missing_on_client": missing_on_client[:20],
            "mismatched": mismatched[:20],
        }, ensure_ascii=False, indent=2))
        return 1

    print(json.dumps({"ok": True, "aligned": len(client)}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
