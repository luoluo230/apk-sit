# -*- coding: utf-8 -*-
"""Generate ProtocolDictionary.cs from protocols.json (utf-8-sig)."""

from __future__ import annotations

import argparse
import json
import os
import sys

HEADER = "// Generated from Assets/Src/Protocols/protocols.json. Do not edit by hand."

MACLIENT_ROOT = os.environ.get("MACLIENT_ROOT", r"E:\maclient")
DEFAULT_PROTOCOLS_JSON = os.path.join(MACLIENT_ROOT, "Assets", "Src", "Protocols", "protocols.json")
DEFAULT_OUTPUT = os.path.join(
    MACLIENT_ROOT, "game-server", "shared", "Protocols", "Generated", "ProtocolDictionary.cs"
)


def _load_message_ids(path: str) -> list[tuple[str, int]]:
    with open(path, encoding="utf-8-sig") as handle:
        payload = json.load(handle)
    if not isinstance(payload, dict):
        raise ValueError("protocols.json root must be an object")

    rows: list[tuple[str, int]] = []
    for name, row in payload.items():
        if not isinstance(row, dict):
            continue
        msg_id = row.get("MessageID")
        if msg_id is None:
            msg_id = row.get("messageId") or row.get("id")
        if msg_id is not None:
            rows.append((str(name), int(msg_id)))

    rows.sort(key=lambda item: (item[1], item[0]))
    return rows


def render_protocol_dictionary(rows: list[tuple[str, int]]) -> str:
    lines = [
        HEADER,
        "using System.Collections.Generic;",
        "",
        "public static class ProtocolDictionary",
        "{",
        "    public static readonly Dictionary<string, int> Protocols = new Dictionary<string, int>",
        "    {",
    ]
    for name, msg_id in rows:
        lines.append(f'        {{ "{name}", {msg_id} }},')
    lines.extend(
        [
            "    };",
            "}",
        ]
    )
    return "\n".join(lines) + "\n"


def _normalize(text: str) -> str:
    if text.startswith("\ufeff"):
        text = text[1:]
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    return text.rstrip("\n") + "\n"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--protocols-json",
        default=DEFAULT_PROTOCOLS_JSON,
        help="Path to protocols.json (read as utf-8-sig)",
    )
    parser.add_argument(
        "--output",
        default=DEFAULT_OUTPUT,
        help="Output ProtocolDictionary.cs path",
    )
    parser.add_argument(
        "--check",
        action="store_true",
        help="Verify output is up to date without writing",
    )
    args = parser.parse_args(argv)

    if not os.path.isfile(args.protocols_json):
        print(f"FAIL: protocols.json not found: {args.protocols_json}", file=sys.stderr)
        return 1

    try:
        rows = _load_message_ids(args.protocols_json)
    except (ValueError, json.JSONDecodeError, OSError) as exc:
        print(f"FAIL: {exc}", file=sys.stderr)
        return 1

    if not rows:
        print("FAIL: no MessageID entries found in protocols.json", file=sys.stderr)
        return 1

    generated = render_protocol_dictionary(rows)

    if args.check:
        if not os.path.isfile(args.output):
            print(f"FAIL: missing generated file: {args.output}", file=sys.stderr)
            return 1
        existing = open(args.output, encoding="utf-8-sig").read()
        if _normalize(existing) != _normalize(generated):
            print(f"FAIL: {args.output} is out of date; rerun codegen_protocol_dictionary.py", file=sys.stderr)
            return 1
        print(json.dumps({"ok": True, "checked": len(rows), "output": args.output}, ensure_ascii=False))
        return 0

    os.makedirs(os.path.dirname(args.output), exist_ok=True)
    with open(args.output, "w", encoding="utf-8", newline="\n") as handle:
        handle.write(generated)
    print(json.dumps({"ok": True, "generated": len(rows), "output": args.output}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
