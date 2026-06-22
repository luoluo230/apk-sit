# -*- coding: utf-8 -*-
"""Generate OpenAPI 3 spec from registered Flask routes (140+ paths)."""

from __future__ import annotations

import json
import os
import re
import sys

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
OUT = os.path.join(ROOT, "static", "openapi.json")
MIN_PATHS = int(os.environ.get("OPENAPI_MIN_PATHS", "140"))

SKIP_PREFIXES = ("/static/",)
SKIP_ENDPOINTS = {"static"}


def _flask_path_to_openapi(rule: str) -> str:
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule)


def _path_params(rule: str) -> list[dict]:
    params: list[dict] = []
    for match in re.finditer(r"<(?:[^:>]+:)?([^>]+)>", rule):
        params.append(
            {
                "name": match.group(1),
                "in": "path",
                "required": True,
                "schema": {"type": "string"},
            }
        )
    return params


def _operation(method: str, endpoint: str, rule: str) -> dict:
    op: dict = {
        "summary": endpoint.replace("_", " "),
        "operationId": f"{endpoint}_{method.lower()}",
        "responses": {
            "200": {"description": "OK"},
            "400": {"description": "Bad request"},
            "401": {"description": "Unauthorized"},
            "403": {"description": "Forbidden"},
            "404": {"description": "Not found"},
        },
    }
    params = _path_params(rule)
    if params:
        op["parameters"] = params
    if method in ("POST", "PUT", "PATCH"):
        op["requestBody"] = {
            "required": False,
            "content": {"application/json": {"schema": {"type": "object"}}},
        }
    return op


def collect_paths() -> dict:
    os.environ.setdefault("APP_PORTAL_MODE", "admin")
    if ROOT not in sys.path:
        sys.path.insert(0, ROOT)
    from app_new import app

    paths: dict = {}
    for rule in sorted(app.url_map.iter_rules(), key=lambda r: r.rule):
        if rule.endpoint in SKIP_ENDPOINTS:
            continue
        if any(rule.rule.startswith(prefix) for prefix in SKIP_PREFIXES):
            continue
        openapi_path = _flask_path_to_openapi(rule.rule)
        methods = sorted(m for m in rule.methods if m not in {"HEAD", "OPTIONS"})
        if not methods:
            continue
        entry = paths.setdefault(openapi_path, {})
        for method in methods:
            entry[method.lower()] = _operation(method, rule.endpoint, rule.rule)
    return paths


def build_spec() -> dict:
    paths = collect_paths()
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "apk-site Admin / Release / Ops API",
            "version": "2.0.0",
            "description": "Auto-generated from Flask url_map (admin portal mode).",
        },
        "paths": paths,
    }


def main() -> int:
    import argparse

    parser = argparse.ArgumentParser(description="Generate or verify OpenAPI spec")
    parser.add_argument("--check", action="store_true", help="Fail if static/openapi.json differs")
    args = parser.parse_args()

    spec = build_spec()
    path_count = len(spec["paths"])
    if path_count < MIN_PATHS:
        print(
            json.dumps(
                {"ok": False, "error": f"path count {path_count} < {MIN_PATHS}"},
                ensure_ascii=False,
            ),
            file=sys.stderr,
        )
        return 1

    if args.check:
        if not os.path.isfile(OUT):
            print(f"FAIL: missing {OUT}; run generate_openapi.py", file=sys.stderr)
            return 1
        with open(OUT, encoding="utf-8") as handle:
            on_disk = json.load(handle)
        if on_disk != spec:
            print(f"FAIL: {OUT} is out of date; rerun generate_openapi.py", file=sys.stderr)
            return 1
        print(json.dumps({"ok": True, "paths": path_count}, ensure_ascii=False))
        return 0

    os.makedirs(os.path.dirname(OUT), exist_ok=True)
    with open(OUT, "w", encoding="utf-8") as handle:
        json.dump(spec, handle, ensure_ascii=False, indent=2)
    print(f"Wrote {path_count} paths to {OUT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
