# -*- coding: utf-8 -*-
"""TLS/wss readiness gate (T-D11): mkcert script + doc present."""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

MACLIENT = Path(os.environ.get("MACLIENT_ROOT", r"E:\maclient"))
GS = MACLIENT / "game-server"


def main() -> int:
    errors: list[str] = []
    mkcert = GS / "docs" / "dev" / "mkcert-dev.ps1"
    doc = GS / "docs" / "tls_configuration.md"
    if not mkcert.is_file():
        errors.append(f"missing {mkcert}")
    if not doc.is_file():
        errors.append(f"missing {doc}")
    ok = not errors
    print(json.dumps({"ok": ok, "errors": errors}, ensure_ascii=False))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
