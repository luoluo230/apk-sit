# -*- coding: utf-8 -*-
"""Module-level shared state/constants from legacy ops.helpers. Plan P1-01."""
from __future__ import annotations

import json

import os

import re

import signal

import socket

import subprocess

import sys

import threading

import time

import uuid

import hashlib

import queue as _queue_mod

from collections import deque

from datetime import datetime, timezone

from typing import Any, Dict, List, Optional, Tuple

from urllib.parse import urlencode

from flask import current_app, has_request_context, jsonify, redirect, render_template, render_template_string, request, session

from config import DATA_DIR

from models.data import (
    approvals_db,
    audit_log_db,
    approve_or_reject,
    create_approval,
    get_approved_approval,
    get_system_config,
    log_audit,
    projects_db,
    set_system_config,
)

from services.authz import admin_required, can_access_module, has_scope, is_admin

from services.business_test_catalog import (
    build_catalog_view,
    delete_custom_plan,
    get_plan,
    list_plans,
    resolve_gateway_endpoint,
    resolve_paths,
    save_custom_plan,
    validate_plan_dict,
)

from services.legacy_gm_bridge_client import LegacyGmBridgeClient
from services.ops.encoding import repair_legacy_node_text, text_has_mojibake
from concurrent.futures import ThreadPoolExecutor, as_completed
import time as _time_mod

import services.ops.constants as _ops_constants

import services.ops.storage as _ops_storage

from services.ops.agent_service import _default_agent_policy, _load_agent_policy, _save_agent_policy


for _mod in (_ops_constants, _ops_storage):
    for _k, _v in vars(_mod).items():
        if not _k.startswith("__"):
            globals()[_k] = _v

ops_gateway = ops_gateway  # re-bind after merge

_client = LegacyGmBridgeClient()

NODE_CONFIG_KEY = "GM_LEGACY_NODES"

GM_ACTION_PATHS = {
    "search_player": "/gm/search-player",
    "player_status": "/gm/player-status",
    "adjust_currency": "/gm/adjust-currency",
    "adjust_item": "/gm/adjust-item",
    "hero_edit": "/gm/hero-edit",
    "stage_update": "/gm/stage-update",
    "idle_recompute": "/gm/idle-recompute",
    "send_mail": "/gm/send-mail",
    "send_broadcast": "/gm/send-broadcast",
    "save_template": "/gm/save-template",
    "save_activity": "/gm/save-activity",
    "save_announcement": "/gm/save-announcement",
    "script_task": "/gm/script-task",
}

_text_has_mojibake = text_has_mojibake

_repair_legacy_node_text = repair_legacy_node_text

_probe_cache: Dict[str, Dict[str, Any]] = {}

_probe_cache_agents: List[Dict[str, Any]] = []

_probe_cache_ts: float = 0.0

_probe_cache_sync_ts: float = 0.0

_probe_cache_lock = threading.Lock()

_probe_change_seq = 0

_sse_subscribers: List[_queue_mod.Queue] = []

_sse_sub_lock = threading.Lock()

_probe_pool = ThreadPoolExecutor(max_workers=10, thread_name_prefix="ops-probe")

PROBE_INTERVAL_SEC = 5.0

PROBE_SYNC_INTERVAL_SEC = 30.0

PM_UI_CSS = (
    '<link rel="stylesheet" href="/static/project_ui/ui-microcopy-cleanup.css?v=20260729-v2">'
    '<link rel="stylesheet" href="/static/project_ui/pm-shell.css?v=20260625-pm9">'
    '<link rel="stylesheet" href="/static/project_ui/pm-kpi.css?v=20260625-pm9">'
    '<link rel="stylesheet" href="/static/project_ui/pm-table.css?v=20260625-pm9">'
    '<link rel="stylesheet" href="/static/project_ui/pm-drawer.css?v=20260625-pm9">'
    '<link rel="stylesheet" href="/static/project_ui/pm-filter-bar.css?v=20260625-pm9">'
    '<link rel="stylesheet" href="/static/project_ui/pm-stepper.css?v=20260625-pm9">'
    '<link rel="stylesheet" href="/static/project_ui/pm-modal.css?v=20260625-pm9">'
)

OPS_SHELL_ASSET_VER = "20260730-release-console-v1"

OPS_WORKSPACE_CSS = (
    '<link rel="stylesheet" href="/static/project_environment_detail.css?v=20260717-workspace-v5">'
    '<link rel="stylesheet" href="/static/ops_workspace_pages.css?v=20260717-workspace-v5">'
)

OPS_COMPACT_CSS = OPS_WORKSPACE_CSS

_DESIGN_DEMO_NODE_IDS = frozenset({"gateway-01", "auth-01", "game-01", "ops-01", "tcp-01", "db-01"})

_DESIGN_DEMO_AGENT_IDS = frozenset({
    "agent-01",
    "agent-gateway-01",
    "agent-auth-01",
    "agent-game-01",
    "agent-ops-01",
    "agent-tcp-01",
    "agent-db-01",
})

_DEMO_TO_RUNTIME_NODE = {
    "gateway-01": "gateway-cn-1",
    "auth-01": "auth-cn-1",
    "game-01": "game-cn-1",
    "ops-01": "ops-cn-1",
    "tcp-01": "tcp-cn-1",
    "db-01": "mongo-db-cn-1",
}

_RUNTIME_MINIMAL_NODE_IDS = frozenset({"gateway-cn-1", "auth-cn-1", "ops-cn-1", "game-cn-1"})

_RUNTIME_INFRA_NODE_IDS = frozenset({"mongo-db-cn-1", "redis-cache-cn-1"})

_CORE_PRESET_IDS = frozenset({
    "gateway_http",
    "auth_service",
    "business_main",
    "ops_service",
    "tcp_transport",
    "pressure_worker",
    "redis_cache",
    "mongo_db",
    "mq_kafka",
    "scheduler_job",
})


_CLUSTER_TOPOLOGY_LAYOUT = {
    "gateway": (72, 48),
    "auth": (72, 248),
    "ops": (320, 248),
    "game": (560, 128),
    "cache": (820, 48),
    "redis": (820, 48),
    "database": (820, 248),
    "mongo": (820, 248),
    "tcp": (820, 328),
    "transport": (820, 328),
}

_RUNTIME_TOPOLOGY_EDGE_SPECS = [
    ("gateway-cn-1", "auth-cn-1", "http:80"),
    ("gateway-cn-1", "ops-cn-1", "http:443"),
    ("auth-cn-1", "game-cn-1", "tcp:5512"),
    ("ops-cn-1", "game-cn-1", "tcp:5512"),
]

_RUNTIME_INFRA_EDGE_SPECS = [
    ("game-cn-1", "redis-cache-cn-1", "structured-auto"),
    ("game-cn-1", "mongo-db-cn-1", "structured-auto"),
]

_CORE_MINIMAL_DEMO_INFRA_EDGE_SPECS = [
    ("game-01", "redis-01", "structured-auto"),
    ("game-01", "db-01", "structured-auto"),
]

_EMBEDDED_CLUSTER_SERVER_TYPES = {"auth", "game"}

_GAMESERVER_PROCESS_SERVICE_IDS = frozenset(
    {"gateway-cn-1", "auth-cn-1", "game-cn-1", "ops-cn-1"}
)

_GAMESERVER_DEFAULT_PORTS: Dict[str, int] = {
    "gateway-cn-1": 15050,
    "ops-cn-1": 5504,
}

_GAMESERVER_TCP_PROBE_PORTS: Dict[str, int] = {
    "gateway-cn-1": 15050,
    "ops-cn-1": 5504,
}

_CLUSTER_RELAY_PROBE_PORTS: Dict[str, int] = {
    "auth-cn-1": 15501,
    "game-cn-1": 15502,
}

_GAMESERVER_START_ORDER: Tuple[str, ...] = ("auth-cn-1", "game-cn-1", "ops-cn-1", "gateway-cn-1")

_cluster_runtime_cache: Dict[str, Any] = {"ts": 0.0, "map": {}}

_CLUSTER_RUNTIME_CACHE_TTL_SEC = 5.0

_probe_bg_started = False

_runtime_orchestrator_lock = threading.Lock()

_AGENT_DETAIL_SERVICE_CACHE_MAX_AGE_SEC = 12.0

_BLUEPRINT_LAYER_BY_PRESET: Dict[str, int] = {
    "gateway_http": 0,
    "auth_service": 1,
    "ops_service": 1,
    "business_main": 2,
    "tcp_transport": 3,
    "scheduler_job": 4,
    "mq_kafka": 4,
    "pressure_worker": 4,
    "redis_cache": 5,
    "mongo_db": 5,
}

_GS_LOG_LINE_RE = re.compile(
    r"^\[(?P<time>[^\]]+)\]\[(?P<level>INFO|WARN|WARNING|ERROR|DEBUG|TRACE|FATAL)\]\[(?P<category>[^\]]*)\]\s*(?P<message>.*)$",
    re.IGNORECASE,
)

_GS_LOG_ERROR_HINT = re.compile(
    r"(?i)(\bfailed\b|\bfailure\b|\bexception\b|\berror\b|\bfatal\b|\bcrash\b|\bunable to\b|\bcannot access\b|\bcreateindexes failed\b)",
)

_GS_LOG_WARN_HINT = re.compile(
    r"(?i)(\bwarning\b|\bwarn\b|partial start|degraded|timeout|skipping protocol)",
)

_GS_LOG_SESSION_START = re.compile(
    r"(游戏服务器框架启动中|框架启动中|GameServer framework starting)",
    re.IGNORECASE,
)

_GS_LOG_LIFECYCLE_HIDE = re.compile(
    r"(注销协议|业务模块停止|已注销所有脚本|正在停止所有服务器|集群已安全退出|检测到配置变更，已重新加载)",
)

_SERVICE_LOG_HINTS: Dict[str, List[str]] = {
    "gateway-cn-1": ["gateway", "websocket"],
    "auth-cn-1": ["auth"],
    "game-cn-1": ["game", "router"],
    "ops-cn-1": ["ops", "http", "daemon", "cluster"],
    "mongo-db-cn-1": ["mongo", "mongosession", "mongod"],
    "redis-cache-cn-1": ["redis", "memurai"],
    "db-01": ["mongo", "mongod", "mongosession"],
}

_gameserver_pid_cache: Dict[str, Tuple[float, int]] = {}

_GAMESERVER_PID_CACHE_TTL_SEC = 5.0

_DAEMON_SESSION_MARK = re.compile(
    r"daemon\s+(?:start|restart)(?:\s+begin|:?\s+skipped)",
    re.IGNORECASE,
)

_GAMESERVER_LAUNCH_GUARD = threading.Lock()

_GAMESERVER_LAUNCH_SLOTS: Dict[str, Dict[str, Any]] = {}

_GAMESERVER_LAUNCH_LOCK_TTL_SEC = 180.0

