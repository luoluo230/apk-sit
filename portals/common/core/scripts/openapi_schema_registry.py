# -*- coding: utf-8 -*-
"""Reusable OpenAPI component schemas and per-route inference rules."""

from __future__ import annotations

import re
from typing import Any, Dict, List, Tuple

REF = "#/components/schemas/"

COMPONENT_SCHEMAS: Dict[str, Dict[str, Any]] = {
    "ApiError": {
        "type": "object",
        "required": ["ok", "error"],
        "properties": {
            "ok": {"type": "boolean", "enum": [False]},
            "error": {"type": "string"},
        },
    },
    "ApiOkEmpty": {
        "type": "object",
        "required": ["ok"],
        "properties": {"ok": {"type": "boolean", "enum": [True]}},
    },
    "JsonObject": {
        "type": "object",
        "additionalProperties": True,
    },
    "JsonArray": {
        "type": "array",
        "items": {"$ref": f"{REF}JsonObject"},
    },
    "ApiOkDataObject": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"$ref": f"{REF}JsonObject"},
        },
    },
    "ApiOkDataArray": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"$ref": f"{REF}JsonArray"},
        },
    },
    "MutationRequest": {
        "type": "object",
        "additionalProperties": True,
        "description": "JSON request body for create/update/action endpoints.",
    },
    "HtmlPageResponse": {
        "type": "string",
        "description": "Rendered HTML page.",
    },
    "BinaryResponse": {
        "type": "string",
        "format": "binary",
    },
    "UserFavorites": {
        "type": "object",
        "properties": {
            "page_favorites": {
                "type": "object",
                "additionalProperties": {"type": "boolean"},
            },
            "project_favorites": {
                "type": "array",
                "items": {"type": "string"},
            },
        },
    },
    "ReleaseOrder": {
        "type": "object",
        "properties": {
            "release_order_id": {"type": "string"},
            "project_id": {"type": "string"},
            "env_key": {"type": "string"},
            "channel_id": {"type": "string"},
            "platform": {"type": "string"},
            "version_id": {"type": "string"},
            "version_name": {"type": "string"},
            "version_code": {"type": "string"},
            "status": {"type": "string"},
            "payload": {"$ref": f"{REF}JsonObject"},
            "bundle_id": {"type": "string"},
        },
    },
    "ReleaseOrderList": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"type": "array", "items": {"$ref": f"{REF}ReleaseOrder"}},
        },
    },
    "ReleaseOrderResponse": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"$ref": f"{REF}ReleaseOrder"},
        },
    },
    "ReleaseJourney": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "env_key": {"type": "string"},
            "channel_id": {"type": "string"},
            "platform": {"type": "string"},
            "current_step": {"type": "integer"},
            "per_platform": {"$ref": f"{REF}JsonObject"},
            "release_strategy": {"type": "string"},
            "gray_ratio": {"type": "string"},
            "rollout_percentage": {"type": "integer"},
            "is_gray_active": {"type": "boolean"},
        },
    },
    "ReleaseJourneyResponse": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"$ref": f"{REF}ReleaseJourney"},
        },
    },
    "ProjectSummary": {
        "type": "object",
        "properties": {
            "project_id": {"type": "string"},
            "project_name": {"type": "string"},
            "status": {"type": "string"},
        },
    },
    "ProjectListResponse": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"type": "array", "items": {"$ref": f"{REF}ProjectSummary"}},
        },
    },
    "VersionRow": {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "version_name": {"type": "string"},
            "version_code": {"type": "string"},
            "platform": {"type": "string"},
            "rollout_percentage": {"type": "integer"},
        },
    },
    "VersionResponse": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"$ref": f"{REF}VersionRow"},
        },
    },
    "BootstrapPayload": {
        "type": "object",
        "properties": {
            "version_name": {"type": "string"},
            "version_code": {"type": "string"},
            "rollout_percentage": {"type": "integer"},
            "force_update": {"type": "boolean"},
            "network_profile": {"$ref": f"{REF}JsonObject"},
            "active_bundle_id": {"type": "string"},
        },
    },
    "BootstrapResponse": {
        "type": "object",
        "required": ["ok"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"$ref": f"{REF}BootstrapPayload"},
        },
    },
    "TopologyRow": {
        "type": "object",
        "properties": {
            "topology_id": {"type": "string"},
            "project_id": {"type": "string"},
            "env_key": {"type": "string"},
            "name": {"type": "string"},
            "status": {"type": "string"},
        },
    },
    "TopologyListResponse": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"type": "array", "items": {"$ref": f"{REF}TopologyRow"}},
        },
    },
    "UserFavoritesResponse": {
        "type": "object",
        "required": ["ok", "data"],
        "properties": {
            "ok": {"type": "boolean", "enum": [True]},
            "data": {"$ref": f"{REF}UserFavorites"},
        },
    },
    "ToggleFavoriteRequest": {
        "type": "object",
        "properties": {
            "key": {"type": "string"},
            "project_id": {"type": "string"},
            "active": {"type": "boolean"},
        },
    },
    "ExpandGrayRequest": {
        "type": "object",
        "properties": {
            "target_ratio": {"type": "integer", "minimum": 1, "maximum": 100},
            "rollout_percentage": {"type": "integer", "minimum": 1, "maximum": 100},
        },
    },
    "VerifyReleaseRequest": {
        "type": "object",
        "properties": {"ok": {"type": "boolean"}},
    },
    "ApproveReleaseRequest": {
        "type": "object",
        "properties": {"note": {"type": "string"}},
    },
    "QuickPublishRequest": {
        "type": "object",
        "properties": {
            "env_key": {"type": "string"},
            "channel_id": {"type": "string"},
            "platform": {"type": "string"},
            "version_id": {"type": "string"},
            "skip_build": {"type": "boolean"},
            "force_build": {"type": "boolean"},
            "auto_verify": {"type": "boolean"},
        },
    },
}

EXACT_ROUTE_SCHEMAS: Dict[Tuple[str, str], Dict[str, str]] = {
    ("/api/user/favorites", "get"): {"response": "UserFavoritesResponse"},
    ("/api/user/favorites", "put"): {"request": "UserFavorites", "response": "UserFavoritesResponse"},
    ("/api/user/favorites/toggle-page", "post"): {"request": "ToggleFavoriteRequest", "response": "UserFavoritesResponse"},
    ("/api/user/favorites/toggle-project", "post"): {"request": "ToggleFavoriteRequest", "response": "UserFavoritesResponse"},
    ("/api/projects/context-catalog", "get"): {"response": "ProjectListResponse"},
    ("/api/projects/{project_id}/release-orders", "get"): {"response": "ReleaseOrderList"},
    ("/api/projects/{project_id}/release-orders", "post"): {"request": "MutationRequest", "response": "ReleaseOrderResponse"},
    ("/api/projects/{project_id}/release-orders/{order_id}", "get"): {"response": "ReleaseOrderResponse"},
    ("/api/projects/{project_id}/release-orders/{order_id}", "patch"): {"request": "MutationRequest", "response": "ReleaseOrderResponse"},
    ("/api/projects/{project_id}/release-orders/{order_id}/publish", "post"): {"request": "MutationRequest", "response": "ReleaseOrderResponse"},
    ("/api/projects/{project_id}/release-orders/{order_id}/expand-gray", "post"): {"request": "ExpandGrayRequest", "response": "ReleaseOrderResponse"},
    ("/api/projects/{project_id}/release-orders/{order_id}/verify", "post"): {"request": "VerifyReleaseRequest", "response": "ReleaseOrderResponse"},
    ("/api/projects/{project_id}/release-orders/{order_id}/approve", "post"): {"request": "ApproveReleaseRequest", "response": "ReleaseOrderResponse"},
    ("/api/projects/{project_id}/environments/{env_key}/channels/{channel_id}/release-journey", "get"): {"response": "ReleaseJourneyResponse"},
    ("/api/projects/{project_id}/environments/{env_key}/channels/{channel_id}/build-journey", "get"): {"response": "ApiOkDataObject"},
    ("/api/projects/{project_id}/delivery-attempts/quick-publish", "post"): {"request": "QuickPublishRequest", "response": "ApiOkDataObject"},
    ("/api/public/runtime-bootstrap", "get"): {"response": "BootstrapResponse"},
    ("/openapi.json", "get"): {"response": "JsonObject"},
}

COMMON_QUERY_PARAMS: Dict[str, Dict[str, Any]] = {
    "platform": {"name": "platform", "in": "query", "schema": {"type": "string"}},
    "version_id": {"name": "version_id", "in": "query", "schema": {"type": "string"}},
    "bundle_id": {"name": "bundle_id", "in": "query", "schema": {"type": "string"}},
    "env_key": {"name": "env_key", "in": "query", "schema": {"type": "string"}},
    "channel_id": {"name": "channel_id", "in": "query", "schema": {"type": "string"}},
    "project_id": {"name": "project_id", "in": "query", "schema": {"type": "string"}},
    "q": {"name": "q", "in": "query", "schema": {"type": "string"}},
    "page": {"name": "page", "in": "query", "schema": {"type": "integer", "minimum": 1}},
    "page_size": {"name": "page_size", "in": "query", "schema": {"type": "integer", "minimum": 1}},
}


def _infer_query_params(path: str, endpoint: str) -> List[Dict[str, Any]]:
    params: List[Dict[str, Any]] = []
    if "/release-journey" in path or "/build-journey" in path:
        params.extend([dict(COMMON_QUERY_PARAMS[k]) for k in ("platform", "version_id", "bundle_id")])
    if "/admin/search" in path:
        params.append(dict(COMMON_QUERY_PARAMS["q"]))
    if endpoint.endswith("_list") or "list_" in endpoint:
        for key in ("env_key", "channel_id", "platform", "project_id", "page", "page_size"):
            if key in path or key.replace("_", "") in endpoint:
                params.append(dict(COMMON_QUERY_PARAMS[key]))
    if "/runtime-bootstrap" in path:
        for key in ("project_id", "env_key", "channel_id", "platform"):
            params.append(dict(COMMON_QUERY_PARAMS[key]))
    return params


def _infer_schemas(path: str, method: str, endpoint: str) -> Dict[str, str]:
    exact = EXACT_ROUTE_SCHEMAS.get((path, method.lower()))
    if exact:
        return exact
    if path.startswith("/api/public/"):
        if "bootstrap" in path:
            return {"response": "BootstrapResponse"}
        return {"response": "ApiOkDataObject"}
    if path.startswith("/api/"):
        if method.lower() in {"post", "put", "patch"}:
            req = "MutationRequest"
            if "verify" in path:
                req = "VerifyReleaseRequest"
            elif "approve" in path:
                req = "ApproveReleaseRequest"
            elif "expand-gray" in path:
                req = "ExpandGrayRequest"
            elif "quick-publish" in path:
                req = "QuickPublishRequest"
            elif "toggle-page" in path or "toggle-project" in path:
                req = "ToggleFavoriteRequest"
            elif "favorites" in path:
                req = "UserFavorites"
            resp = "ReleaseOrderResponse" if "release-orders" in path else "ApiOkDataObject"
            return {"request": req, "response": resp}
        if method.lower() == "get":
            if "release-orders" in path and "{" not in path.split("release-orders")[-1]:
                return {"response": "ReleaseOrderList"}
            if "release-orders" in path:
                return {"response": "ReleaseOrderResponse"}
            if "topology" in path:
                return {"response": "TopologyListResponse"}
            if "projects" in path and path.endswith("/projects") or "context-catalog" in path:
                return {"response": "ProjectListResponse"}
            if "versions" in path and "{version_id}" in path:
                return {"response": "VersionResponse"}
            return {"response": "ApiOkDataObject"}
        if method.lower() == "delete":
            return {"response": "ApiOkEmpty"}
    if path.endswith(".json") or path.endswith(".xml") or "/download" in path:
        return {"response": "BinaryResponse"}
    return {"response": "HtmlPageResponse"}


def _json_response(schema_name: str, description: str = "OK") -> Dict[str, Any]:
    if schema_name == "HtmlPageResponse":
        return {
            "description": description,
            "content": {"text/html": {"schema": {"$ref": f"{REF}HtmlPageResponse"}}},
        }
    if schema_name == "BinaryResponse":
        return {
            "description": description,
            "content": {"application/octet-stream": {"schema": {"$ref": f"{REF}BinaryResponse"}}},
        }
    return {
        "description": description,
        "content": {"application/json": {"schema": {"$ref": f"{REF}{schema_name}"}}},
    }


def enrich_operation(method: str, endpoint: str, rule: str, op: Dict[str, Any]) -> Dict[str, Any]:
    path = _flask_path_to_openapi(rule)
    schemas = _infer_schemas(path, method, endpoint)
    params = list(op.get("parameters") or [])
    for qp in _infer_query_params(path, endpoint):
        if not any(p.get("name") == qp.get("name") and p.get("in") == "query" for p in params):
            params.append(qp)
    if params:
        op["parameters"] = params
    if method in ("POST", "PUT", "PATCH") and "request" in schemas:
        op["requestBody"] = {
            "required": method in ("POST", "PUT"),
            "content": {
                "application/json": {"schema": {"$ref": f"{REF}{schemas['request']}"}},
            },
        }
    response_schema = schemas.get("response", "ApiOkDataObject")
    op["responses"] = {
        "200": _json_response(response_schema, "OK"),
        "201": _json_response(response_schema, "Created"),
        "400": _json_response("ApiError", "Bad request"),
        "401": _json_response("ApiError", "Unauthorized"),
        "403": _json_response("ApiError", "Forbidden"),
        "404": _json_response("ApiError", "Not found"),
    }
    if not path.startswith("/api/"):
        op["responses"]["200"] = _json_response("HtmlPageResponse", "OK")
    tags = op.setdefault("tags", [])
    if path.startswith("/api/public/"):
        tags.append("public")
    elif path.startswith("/api/projects/"):
        tags.append("projects")
    elif path.startswith("/api/user/"):
        tags.append("user")
    elif path.startswith("/api/gm-ops/"):
        tags.append("gm-ops")
    elif path.startswith("/admin/ops"):
        tags.append("ops")
    elif path.startswith("/admin/"):
        tags.append("admin")
    elif path.startswith("/api/"):
        tags.append("api")
    else:
        tags.append("portal")
    op["tags"] = sorted(set(tags))
    return op


def _flask_path_to_openapi(rule: str) -> str:
    return re.sub(r"<(?:[^:>]+:)?([^>]+)>", r"{\1}", rule)


def build_components() -> Dict[str, Any]:
    return {"schemas": COMPONENT_SCHEMAS}
