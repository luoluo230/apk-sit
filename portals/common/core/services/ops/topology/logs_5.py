def _load_topology(current_nodes: Optional[List[Dict[str, Any]]] = None) -> Dict[str, Any]:
    rows = current_nodes if isinstance(current_nodes, list) else _load_nodes()
    raw = get_system_config(OPS_TOPOLOGY_KEY, {})
    if isinstance(raw, dict):
        nodes = raw.get("nodes") if isinstance(raw.get("nodes"), list) else []
        edges = raw.get("edges") if isinstance(raw.get("edges"), list) else []
        meta = raw.get("meta") if isinstance(raw.get("meta"), dict) else {}
    else:
        nodes, edges, meta = [], [], {}

    valid_ids = set([str(x.get("id") or "") for x in rows if isinstance(x, dict)])
    merged_nodes: List[Dict[str, Any]] = []
    seen = set()
    for item in nodes:
        if not isinstance(item, dict):
            continue
        nid = str(item.get("id") or "").strip()
        if not nid or nid not in valid_ids or nid in seen:
            continue
        seen.add(nid)
        merged_nodes.append(
            {
                "id": nid,
                "role": str(item.get("role") or "business"),
                "kind": _infer_node_kind(str(item.get("role") or "business"), str(item.get("kind") or "")),
                "desc": str(item.get("desc") or ""),
                "bizStatus": str(item.get("bizStatus") or "normal"),
                "owner": str(item.get("owner") or ""),
                "x": float(item.get("x") or 0),
                "y": float(item.get("y") or 0),
                "tags": item.get("tags") if isinstance(item.get("tags"), list) else [],
                "ui": item.get("ui") if isinstance(item.get("ui"), dict) else {},
            }
        )
    if len(merged_nodes) < len(valid_ids):
        default_topo = _default_topology_for_nodes(rows)
        for item in default_topo.get("nodes") or []:
            nid = str(item.get("id") or "")
            if nid and nid not in seen:
                merged_nodes.append(item)
                seen.add(nid)

    merged_edges: List[Dict[str, Any]] = []
    for edge in edges:
        if not isinstance(edge, dict):
            continue
        frm = str(edge.get("from") or "").strip()
        to = str(edge.get("to") or "").strip()
        if not frm or not to or frm not in valid_ids or to not in valid_ids:
            continue
        merged_edges.append(
            {
                "id": str(edge.get("id") or f"edge-{uuid.uuid4().hex[:10]}"),
                "from": frm,
                "to": to,
                "from_port": str(edge.get("from_port") or "out-1"),
                "to_port": str(edge.get("to_port") or "in-1"),
                "type": str(edge.get("type") or "depends_on"),
                "note": str(edge.get("note") or ""),
                "ui": edge.get("ui") if isinstance(edge.get("ui"), dict) else {},
            }
        )
    for n in merged_nodes:
        if not isinstance(n, dict):
            continue
        kind = _infer_node_kind(str(n.get("role") or ""), str(n.get("kind") or ""))
        n["kind"] = kind
        ui = n.get("ui") if isinstance(n.get("ui"), dict) else {}
        ui["ports"] = _normalize_ports(kind, ui.get("ports"))
        if "w" not in ui:
            ui["w"] = 220
        if "h" not in ui:
            ui["h"] = 90
        n["ui"] = ui
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    out_meta = {
        "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
        "version": int(meta.get("version") or 1),
        "updated_at": str(meta.get("updated_at") or ""),
    }
    return {"nodes": merged_nodes, "edges": merged_edges, "meta": out_meta}


def _save_topology(topology: Dict[str, Any]) -> Dict[str, Any]:
    nodes = topology.get("nodes") if isinstance(topology, dict) and isinstance(topology.get("nodes"), list) else []
    edges = topology.get("edges") if isinstance(topology, dict) and isinstance(topology.get("edges"), list) else []
    meta = topology.get("meta") if isinstance(topology, dict) and isinstance(topology.get("meta"), dict) else {}
    viewport = meta.get("viewport") if isinstance(meta.get("viewport"), dict) else {}
    payload = {
        "nodes": nodes,
        "edges": edges,
        "meta": {
            "viewport": {"x": float(viewport.get("x") or 0), "y": float(viewport.get("y") or 0), "zoom": float(viewport.get("zoom") or 1)},
            "version": int(meta.get("version") or 1),
            "updated_at": _now_iso(),
        },
        "updated_at": _now_iso(),
    }
    _save_json_config(OPS_TOPOLOGY_KEY, payload, description="Ops 平台拓扑配置")
    return payload


def _apply_topology_blueprint_edges(
    topo: Dict[str, Any],
    created_by_preset: Dict[str, List[str]],
    plan_edges: List[Any],
) -> None:
    if not isinstance(topo.get("edges"), list):
        topo["edges"] = []
    existing = topo["edges"]
    for rel in plan_edges or []:
        spec = _normalize_blueprint_edge_rel(rel)
        if not spec:
            continue
        s_nodes = created_by_preset.get(str(spec.get("from") or "")) or []
        t_nodes = created_by_preset.get(str(spec.get("to") or "")) or []
        if not s_nodes or not t_nodes:
            continue
        for sid, tid in _blueprint_edge_instance_pairs(s_nodes, t_nodes, str(spec.get("mode") or "round_robin")):
            dup = False
            for edge in existing:
                if not isinstance(edge, dict):
                    continue
                if (
                    str(edge.get("from") or "") == sid
                    and str(edge.get("to") or "") == tid
                    and str(edge.get("from_port") or "out-1") == str(spec.get("from_port") or "out-1")
                ):
                    dup = True
                    break
            if dup:
                continue
            existing.append(
                {
                    "id": f"edge-{uuid.uuid4().hex[:10]}",
                    "from": sid,
                    "to": tid,
                    "from_port": str(spec.get("from_port") or "out-1"),
                    "to_port": str(spec.get("to_port") or "in-1"),
                    "type": str(spec.get("type") or "depends_on"),
                    "note": str(spec.get("note") or "blueprint-auto"),
                }
            )


def _default_topology_blueprints() -> List[Dict[str, Any]]:
    core_edges = _commercial_framework_core_edges()
    return [
        {
            "blueprint_id": "minimal_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "最小框架",
            "desc": "通用游戏服最小栈：入口网关、认证、运维控制、业务逻辑、缓存与主库；适合单机/开发/小规模上线",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
            ],
            "edges": list(core_edges),
        },
        {
            "blueprint_id": "medium_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "中型框架",
            "desc": "通用中型架构：最小栈 + 业务水平扩展、异步消息与定时调度；适合常规商业服与多实例部署",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 2},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": list(core_edges)
            + [
                {"from": "business_main", "to": "mq_kafka", "note": "async-events", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "business_main", "note": "batch-jobs", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "mongo_db", "note": "batch-read", "mode": "each_to_first"},
            ],
        },
        {
            "blueprint_id": "full_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "全量框架",
            "desc": "通用大型架构：多入口、控制面、多业务实例、实时传输、消息与调度；适合完整运维链路与生产扩展",
            "framework_profile": "commercial_game_server",
            "nodes": [
                {"preset_id": "gateway_http", "count": 2},
                {"preset_id": "auth_service", "count": 1},
                {"preset_id": "ops_service", "count": 1},
                {"preset_id": "business_main", "count": 3},
                {"preset_id": "tcp_transport", "count": 1},
                {"preset_id": "scheduler_job", "count": 1},
                {"preset_id": "redis_cache", "count": 1},
                {"preset_id": "mongo_db", "count": 1},
                {"preset_id": "mq_kafka", "count": 1},
            ],
            "edges": list(core_edges)
            + [
                {"from": "business_main", "to": "tcp_transport", "note": "tcp:realtime", "mode": "each_to_all"},
                {"from": "business_main", "to": "mq_kafka", "note": "async-events", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "business_main", "note": "batch-jobs", "mode": "each_to_all"},
                {"from": "scheduler_job", "to": "mongo_db", "note": "batch-read", "mode": "each_to_first"},
            ],
        },
        {
            "blueprint_id": "pressure_test_framework",
            "blueprint_version": _TOPOLOGY_BLUEPRINT_FRAMEWORK_VERSION,
            "name": "压测框架",
            "desc": "压测专用（非生产）：入口网关 + 业务节点 + 压测 Worker；不含 Auth/Ops/缓存/数据库，与商业生产模板隔离",
            "framework_profile": "pressure_test",
            "nodes": [
                {"preset_id": "gateway_http", "count": 1},
                {"preset_id": "business_main", "count": 1},
                {"preset_id": "pressure_worker", "count": 1},
            ],
            "edges": [
                {"from": "gateway_http", "to": "business_main", "from_port": "out-1", "note": "http:load-entry", "mode": "each_to_all"},
                {"from": "pressure_worker", "to": "business_main", "note": "stress:qps", "mode": "each_to_all"},
            ],
        },
    ]


def _merge_topology_blueprints_with_defaults(stored: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], bool]:
    defaults = _default_topology_blueprints()
    default_by_id = {str(d.get("blueprint_id") or ""): d for d in defaults}
    stored_by_id = {
        str(x.get("blueprint_id") or ""): x
        for x in stored
        if isinstance(x, dict) and str(x.get("blueprint_id") or "").strip()
    }
    merged: List[Dict[str, Any]] = []
    changed = False
    for default_row in defaults:
        bid = str(default_row.get("blueprint_id") or "")
        old = stored_by_id.get(bid)
        old_ver = int(old.get("blueprint_version") or 0) if isinstance(old, dict) else 0
        new_ver = int(default_row.get("blueprint_version") or 0)
        if isinstance(old, dict) and old_ver >= new_ver:
            merged.append(old)
        else:
            merged.append(default_row)
            changed = True
    for bid, row in stored_by_id.items():
        if bid not in default_by_id:
            merged.append(row)
    if not stored:
        changed = True
    return merged, changed


def _load_topology_blueprints() -> List[Dict[str, Any]]:
    raw = get_system_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, [])
    stored: List[Dict[str, Any]] = []
    if isinstance(raw, list):
        for item in raw:
            if isinstance(item, dict) and str(item.get("blueprint_id") or "").strip():
                stored.append(item)
    merged, changed = _merge_topology_blueprints_with_defaults(stored)
    if changed or not stored:
        _save_json_config(OPS_TOPOLOGY_BLUEPRINTS_KEY, merged, description="Ops topology blueprints")
    return merged


def _normalize_log_level(level: str) -> str:
    lv = str(level or "").strip().upper()
    if lv in ("WARN", "WARNING"):
        return "warn"
    if lv in ("ERROR", "FATAL"):
        return "error"
    if lv in ("DEBUG", "TRACE"):
        return "debug"
    return "info"


def _infer_log_level_from_text(level: str, raw_line: str, source_path: str = "") -> str:
    normalized = _normalize_log_level(level)
    if normalized in ("warn", "error", "debug"):
        return normalized
    text = str(raw_line or "")
    if _GS_LOG_ERROR_HINT.search(text):
        return "error"
    if _GS_LOG_WARN_HINT.search(text):
        return "warn"
    if str(source_path or "").endswith(".err.log"):
        return "error"
    return "info"


def _log_dedupe_key(raw_line: str) -> str:
    text = str(raw_line or "").strip()
    if not text:
        return ""
    stripped = re.sub(r"^\[[^\]]+\]", "", text, count=1).strip()
    stripped = re.sub(r"^\[(INFO|WARN|WARNING|ERROR|DEBUG|TRACE|FATAL)\]", "", stripped, flags=re.IGNORECASE).strip()
    stripped = re.sub(r"^\[[^\]]+\]", "", stripped, count=1).strip()
    return stripped.lower()


def _service_log_line_matches(service_id: str, parsed: Dict[str, Any], raw_line: str) -> bool:
    sid = str(service_id or "").strip().lower()
    if not sid:
        return True
    hints = _SERVICE_LOG_HINTS.get(sid) or []
    if not hints:
        token = sid.split("-")[0]
        hints = [token] if token else []
    hay = f"{parsed.get('category') or ''} {parsed.get('message') or ''} {raw_line}".lower()
    if sid in hay:
        return True
    return any(h in hay for h in hints)


def _log_line_epoch(raw_line: str) -> float:
    text = str(raw_line or "")
    match = re.search(r"(\d{4}-\d{2}-\d{2}[ T]\d{2}:\d{2}:\d{2}(?:\.\d+)?)", text)
    if not match:
        return 0.0
    token = match.group(1).replace(" ", "T")
    tail = text[match.end(): match.end() + 2]
    if tail.startswith("Z") or text[match.start(): match.end()].endswith("Z"):
        token += "Z"
    try:
        if token.endswith("Z"):
            return datetime.fromisoformat(token.replace("Z", "+00:00")).timestamp()
        return datetime.fromisoformat(token).replace(tzinfo=timezone.utc).timestamp()
    except ValueError:
        return 0.0


def _should_hide_lifecycle_log_line(raw_line: str) -> bool:
    text = str(raw_line or "")
    if not text.strip():
        return True
    return bool(_GS_LOG_LIFECYCLE_HIDE.search(text))


def _ops_topology_meta_structured(topo: Dict[str, Any]) -> None:
    meta = topo.get("meta") if isinstance(topo.get("meta"), dict) else {}
    spacing = meta.get("layout_spacing") if isinstance(meta.get("layout_spacing"), dict) else None
    spacing_customized = bool(meta.get("layout_spacing_customized"))
    meta["layout_mode"] = "structured"
    meta["updated_at"] = _now_iso()
    if spacing is not None:
        meta["layout_spacing"] = _normalize_layout_spacing(spacing)
    if spacing_customized:
        meta["layout_spacing_customized"] = True
    topo["meta"] = meta


def _ops_topology_node_map(topo: Dict[str, Any]) -> Dict[str, Dict[str, Any]]:
    return {str(n.get("id") or ""): n for n in (topo.get("nodes") or []) if isinstance(n, dict) and str(n.get("id") or "")}


def _ops_topology_edge_list(topo: Dict[str, Any]) -> List[Dict[str, Any]]:
    edges = topo.get("edges") if isinstance(topo.get("edges"), list) else []
    topo["edges"] = edges
    return edges
