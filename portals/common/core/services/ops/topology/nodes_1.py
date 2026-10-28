def _normalize_node(payload: Dict[str, Any]) -> Dict[str, Any]:
    node_id = str(payload.get("id") or uuid.uuid4().hex[:12]).strip()
    fallback_ops_base = str(
        payload.get("ops_base_url")
        or os.getenv("GM_LEGACY_OPS_BASE_URL", "")
        or payload.get("base_url")
        or os.getenv("GM_LEGACY_BASE_URL", "")
        or "http://127.0.0.1:5054"
        or ""
    ).strip()
    return {
        "id": node_id,
        "name": str(payload.get("name") or node_id).strip(),
        "base_url": str(payload.get("base_url") or "").strip(),
        "ops_base_url": fallback_ops_base,
        "ops_read_key": str(payload.get("ops_read_key") or "").strip(),
        "ops_write_key": str(payload.get("ops_write_key") or "").strip(),
        "ops_actor": str(payload.get("ops_actor") or "").strip(),
        "ops_role": str(payload.get("ops_role") or "").strip(),
        "username": str(payload.get("username") or "").strip(),
        "password": str(payload.get("password") or "").strip(),
        "server_id": str(payload.get("server_id") or "").strip(),
        "project_id": str(payload.get("project_id") or "").strip(),
        "owner": str(payload.get("owner") or "").strip(),
        "role": str(payload.get("role") or "business").strip(),
        "node_category": str(payload.get("node_category") or "").strip(),
        "node_type": str(payload.get("node_type") or "").strip(),
        "description": str(payload.get("description") or "").strip(),
        "biz_status": str(payload.get("biz_status") or "normal").strip(),
        "allowed_upstream_roles": payload.get("allowed_upstream_roles") if isinstance(payload.get("allowed_upstream_roles"), list) else [],
        "allowed_downstream_roles": payload.get("allowed_downstream_roles") if isinstance(payload.get("allowed_downstream_roles"), list) else [],
        "daemon_profile": str(payload.get("daemon_profile") or "").strip(),
        "daemon_start_cmd": str(payload.get("daemon_start_cmd") or "").strip(),
        "daemon_stop_cmd": str(payload.get("daemon_stop_cmd") or "").strip(),
        "env": str(payload.get("env") or "").strip(),
        "channel": str(payload.get("channel") or "").strip(),
        "enabled": bool(payload.get("enabled", True)),
        "tags": payload.get("tags") if isinstance(payload.get("tags"), list) else [],
    }


def _default_nodes() -> List[Dict[str, Any]]:
    base_url = str(os.getenv("GM_LEGACY_BASE_URL", "http://127.0.0.1:8080")).strip()
    ops_base_url = str(os.getenv("GM_LEGACY_OPS_BASE_URL", "http://127.0.0.1:5054")).strip()
    ops_read_key = str(os.getenv("GM_LEGACY_OPS_READ_KEY", "2062f00689b2abee75b9bab1bd49f435c57e580d14db436942374d09a5d5468a")).strip()
    ops_write_key = str(os.getenv("GM_LEGACY_OPS_WRITE_KEY", "2062f00689b2abee75b9bab1bd49f435c57e580d14db436942374d09a5d5468a")).strip()
    ops_actor = str(os.getenv("GM_LEGACY_OPS_ACTOR", "intranet-ops")).strip()
    ops_role = str(os.getenv("GM_LEGACY_OPS_ROLE", "SuperAdmin")).strip()
    username = str(os.getenv("GM_LEGACY_USERNAME", "gm")).strip()
    password = str(os.getenv("GM_LEGACY_PASSWORD", "")).strip()
    return [
        _normalize_node(
            {
                "id": "local-gm",
                "name": "本地GM节点",
                "base_url": base_url,
                "ops_base_url": ops_base_url,
                "ops_read_key": ops_read_key,
                "ops_write_key": ops_write_key,
                "ops_actor": ops_actor,
                "ops_role": ops_role,
                "username": username,
                "password": password,
                "server_id": "",
                "role": "business",
                "node_category": "application",
                "node_type": "business_server",
                "description": "默认节点",
                "biz_status": "normal",
                "allowed_upstream_roles": ["gateway", "scheduler", "admin"],
                "allowed_downstream_roles": ["database", "cache", "mq", "search"],
                "daemon_profile": "ops_native",
                "enabled": True,
            }
        )
    ]


def _repair_legacy_node_text(item: Dict[str, Any]) -> Dict[str, Any]:
    row = dict(item or {})
    name = str(row.get("name") or "")
    desc = str(row.get("description") or "")
    if _text_has_mojibake(name):
        if str(row.get("id") or "") == "local-gm":
            row["name"] = "本地GM节点"
        else:
            row["name"] = str(row.get("id") or "节点")
    if _text_has_mojibake(desc):
        row["description"] = "默认节点"
    return row


def _load_nodes() -> List[Dict[str, Any]]:
    raw = get_system_config(NODE_CONFIG_KEY, [])
    if isinstance(raw, list) and raw:
        rows: List[Dict[str, Any]] = []
        changed = False
        for item in raw:
            if isinstance(item, dict):
                repaired = _repair_legacy_node_text(item)
                if repaired != item:
                    changed = True
                rows.append(_normalize_node(repaired))
        if rows:
            if changed:
                _save_nodes(rows)
            return rows
    return _default_nodes()


def _save_nodes(rows: List[Dict[str, Any]]) -> None:
    normalized = [_normalize_node(item if isinstance(item, dict) else {}) for item in (rows or [])]
    set_system_config(
        NODE_CONFIG_KEY,
        normalized,
        value_type="json",
        description="Legacy GM + Ops 节点配置",
        username="system",
    )


def _resolve_node(node_id: str = "", project_id: str = "", env: str = "", channel: str = "") -> Optional[Dict[str, Any]]:
    rows = _load_nodes()
    enabled = [x for x in rows if x.get("enabled")]
    if node_id:
        for item in rows:
            if str(item.get("id") or "") == node_id:
                return item
    if project_id:
        for item in enabled:
            if str(item.get("project_id") or "") == project_id:
                if env and str(item.get("env") or "") not in ("", env):
                    continue
                if channel and str(item.get("channel") or "") not in ("", channel):
                    continue
                return item
    return enabled[0] if enabled else (rows[0] if rows else None)


def _node_or_400(payload: Dict[str, Any]):
    node = _resolve_flow_test_node(payload)
    if not node:
        return None, (jsonify({"ok": False, "error": "no node configured"}), 400)
    return node, None


def _strip_default_node_ui_color(ui: Dict[str, Any]) -> Dict[str, Any]:
    out = dict(ui or {})
    if str(out.get("color") or "").strip().lower() == "#0f172a":
        out.pop("color", None)
    return out


def _enrich_preset_from_contract(preset: Dict[str, Any]) -> Dict[str, Any]:
    if not isinstance(preset, dict):
        return preset
    pid = str(preset.get("preset_id") or "").strip()
    contract = _load_node_contract(pid) if pid else None
    out = dict(preset)
    if isinstance(contract, dict):
        if not out.get("default_port") and contract.get("default_port"):
            out["default_port"] = int(contract.get("default_port") or 0)
        if not out.get("probe_strategy") and contract.get("probe_strategy"):
            out["probe_strategy"] = str(contract.get("probe_strategy") or "")
        if contract.get("role") and str(out.get("role") or "") == "admin":
            out["role"] = str(contract.get("role") or out.get("role") or "")
        if contract.get("execution_model") in ("daemon", "worker"):
            out["daemon_profile"] = "external_daemon"
    return out


def _default_node_presets() -> List[Dict[str, Any]]:
    raw = [
        {
            "preset_id": "gateway_http",
            "name": "网关服务",
            "category": "application",
            "role": "gateway",
            "node_type": "gateway_server",
            "default_desc": "入口网关，承接流量并转发业务服务",
            "fixed_upstream_roles": ["edge", "lb", "admin", "ops"],
            "fixed_downstream_roles": ["business", "pressure", "auth"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "auth_service",
            "name": "认证服务",
            "category": "application",
            "role": "auth",
            "node_type": "auth_server",
            "default_desc": "用户认证与会话校验服务",
            "fixed_upstream_roles": ["gateway", "edge"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "business_main",
            "name": "游戏服务",
            "category": "application",
            "role": "business",
            "node_type": "business_server",
            "default_desc": "核心业务处理节点",
            "fixed_upstream_roles": ["gateway", "scheduler", "admin", "ops", "auth"],
            "fixed_downstream_roles": ["database", "cache", "mq", "search", "transport"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "ops_service",
            "name": "运维服务",
            "category": "application",
            "role": "ops",
            "node_type": "ops_server",
            "default_desc": "运维控制与诊断服务",
            "fixed_upstream_roles": ["gateway", "edge"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "tcp_transport",
            "name": "传输服务",
            "category": "network",
            "role": "transport",
            "node_type": "tcp_transport",
            "default_desc": "TCP 长连接传输节点",
            "fixed_upstream_roles": ["business", "gateway"],
            "fixed_downstream_roles": [],
            "daemon_profile": "ops_native",
        },
        {
            "preset_id": "pressure_worker",
            "name": "压测服务",
            "category": "test",
            "role": "pressure",
            "node_type": "pressure_server",
            "default_desc": "压测流量与性能回归节点",
            "fixed_upstream_roles": ["gateway", "admin", "ops"],
            "fixed_downstream_roles": ["business"],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "redis_cache",
            "name": "Redis 缓存",
            "category": "infrastructure",
            "role": "cache",
            "node_type": "redis_cache",
            "default_desc": "缓存与会话存储节点",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mongo_db",
            "name": "Mongo Database",
            "category": "database",
            "role": "database",
            "node_type": "mongo_database",
            "default_desc": "业务主存储数据库",
            "fixed_upstream_roles": ["business", "scheduler", "admin", "ops"],
            "fixed_downstream_roles": [],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "mq_kafka",
            "name": "消息队列",
            "category": "infrastructure",
            "role": "mq",
            "node_type": "mq_kafka",
            "default_desc": "异步事件队列",
            "fixed_upstream_roles": ["business", "gateway", "scheduler"],
            "fixed_downstream_roles": ["business", "analytics"],
            "daemon_profile": "external_daemon",
        },
        {
            "preset_id": "scheduler_job",
            "name": "调度服务",
            "category": "application",
            "role": "scheduler",
            "node_type": "scheduler_server",
            "default_desc": "定时任务与批处理节点",
            "fixed_upstream_roles": ["admin", "ops"],
            "fixed_downstream_roles": ["business", "database", "cache", "mq"],
            "daemon_profile": "external_daemon",
        },
    ]
    return [_enrich_preset_from_contract(x) for x in raw]


def _load_node_presets() -> List[Dict[str, Any]]:
    defaults = _default_node_presets()
    default_by_id = {str(p.get("preset_id") or "").strip(): p for p in defaults if str(p.get("preset_id") or "").strip()}
    raw = get_system_config(OPS_NODE_PRESETS_KEY, [])
    if isinstance(raw, list) and raw:
        out: List[Dict[str, Any]] = []
        seen: set = set()
        for item in raw:
            if isinstance(item, dict) and str(item.get("preset_id") or "").strip():
                pid = str(item.get("preset_id") or "").strip()
                if pid == "mysql_db":
                    continue
                seen.add(pid)
                out.append(_enrich_preset_from_contract(item))
        if out:
            if any(_text_has_mojibake(str(x.get("name") or "") + str(x.get("default_desc") or "")) for x in out):
                _save_json_config(OPS_NODE_PRESETS_KEY, defaults, description="Ops node preset catalog")
                return defaults
            missing_core = [pid for pid in _CORE_PRESET_IDS if pid not in seen]
            if missing_core:
                merged = list(out)
                for pid in missing_core:
                    preset = default_by_id.get(pid)
                    if preset:
                        merged.append(preset)
                _save_json_config(OPS_NODE_PRESETS_KEY, merged, description="Ops node preset catalog")
                return merged
            return out
    presets = _default_node_presets()
    _save_json_config(OPS_NODE_PRESETS_KEY, presets, description="Ops node preset catalog")
    return presets


def _preset_role_rules(role: str) -> Dict[str, List[str]]:
    r = str(role or "").strip().lower()
    up: set = set()
    down: set = set()
    for preset in _load_node_presets():
        if str(preset.get("role") or "").strip().lower() != r:
            continue
        for item in (preset.get("fixed_upstream_roles") or []):
            up.add(str(item))
        for item in (preset.get("fixed_downstream_roles") or []):
            down.add(str(item))
    return {"allowed_upstream_roles": sorted(up), "allowed_downstream_roles": sorted(down)}


def _link_role_block_reason(from_node: Dict[str, Any], to_node: Dict[str, Any]) -> str:
    frm = _connect_rule_meta(from_node or {})
    to = _connect_rule_meta(to_node or {})
    from_role = str(frm.get("role") or "").strip().lower()
    to_role = str(to.get("role") or "").strip().lower()
    allow_down = [str(x).strip().lower() for x in (frm.get("allowed_downstream_roles") or []) if str(x).strip()]
    allow_up = [str(x).strip().lower() for x in (to.get("allowed_upstream_roles") or []) if str(x).strip()]
    if allow_down and to_role and to_role not in allow_down:
        return f"「{from_role}」不允许连接「{to_role}」（可连下游：{', '.join(allow_down)}）"
    if allow_up and from_role and from_role not in allow_up:
        return f"「{to_role}」不接受来自「{from_role}」（可接受上游：{', '.join(allow_up)}）"
    return ""


def _can_link_nodes(from_node: Dict[str, Any], to_node: Dict[str, Any]) -> bool:
    return not _link_role_block_reason(from_node, to_node)


def _infer_node_kind(role: str, explicit_kind: str = "") -> str:
    ek = str(explicit_kind or "").strip().lower()
    if ek in ("entry", "standard", "terminal"):
        return ek
    r = str(role or "").strip().lower()
    if r in ("gateway", "edge"):
        return "entry"
    if r in ("database", "cache", "mq", "search", "transport", "tcp"):
        return "terminal"
    return "standard"


def _default_ports_for_kind(kind: str) -> Dict[str, List[Dict[str, Any]]]:
    k = _infer_node_kind("", kind)
    if k == "entry":
        return {"in": [], "out": [{"id": "out-1", "label": "out-1", "kind": "out", "max_links": 1}]}
    if k == "terminal":
        return {"in": [{"id": "in-1", "label": "in-1", "kind": "in", "max_links": 1}], "out": []}
    return {
        "in": [{"id": "in-1", "label": "in-1", "kind": "in", "max_links": 1}],
        "out": [{"id": "out-1", "label": "out-1", "kind": "out", "max_links": 1}],
    }
