# -*- coding: utf-8 -*-
"""Extract module-level state from helpers.py.bak into shared_bootstrap.py."""

from __future__ import annotations

import ast
import os

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
BAK = os.path.join(ROOT, "services", "ops", "helpers.py.bak")
OUT = os.path.join(ROOT, "services", "ops", "shared_bootstrap.py")
MODULES = (
    "diagnostics",
    "topology_contracts",
    "cluster_importer",
    "topology_registry",
    "agent_registry",
    "runtime_orchestrator",
)


def main() -> int:
    with open(BAK, encoding="utf-8") as fp:
        src = fp.read()
    lines = src.splitlines(keepends=True)
    tree = ast.parse(src)
    parts = [
        "# -*- coding: utf-8 -*-",
        '"""Module-level shared state/constants from legacy ops.helpers. Plan P1-01."""',
        "from __future__ import annotations",
        "",
    ]
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            break
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            parts.append("".join(lines[node.lineno - 1 : node.end_lineno]))
    parts.append("")
    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            continue
        if isinstance(node, (ast.Assign, ast.AnnAssign)):
            parts.append("".join(lines[node.lineno - 1 : node.end_lineno]))
        elif isinstance(node, ast.For):
            text = "".join(lines[node.lineno - 1 : node.end_lineno])
            if "globals()" in text:
                parts.append(text)
    with open(OUT, "w", encoding="utf-8") as fp:
        fp.write("\n".join(parts) + "\n")
    print(f"wrote {OUT}")

    bootstrap_import = "from services.ops.shared_bootstrap import *  # noqa: F403\n"
    for name in MODULES:
        path = os.path.join(ROOT, "services", "ops", f"{name}.py")
        with open(path, encoding="utf-8") as fp:
            body = fp.read()
        if "shared_bootstrap" in body:
            continue
        marker = "from __future__ import annotations\n\n"
        if marker in body:
            body = body.replace(marker, marker + bootstrap_import, 1)
        else:
            body = bootstrap_import + body
        with open(path, "w", encoding="utf-8") as fp:
            fp.write(body)
        print(f"patched {path}")

    helpers = os.path.join(ROOT, "services", "ops", "helpers.py")
    with open(helpers, encoding="utf-8") as fp:
        body = fp.read()
    if "shared_bootstrap" not in body:
        body = body.replace(
            "from __future__ import annotations\n\n",
            "from __future__ import annotations\n\nfrom services.ops.shared_bootstrap import *  # noqa: F403\n\n",
            1,
        )
        with open(helpers, "w", encoding="utf-8") as fp:
            fp.write(body)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
