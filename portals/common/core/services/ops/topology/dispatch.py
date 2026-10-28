def _resolve_ops_dispatch_node(project_id: str, node_id: str, env_key: str = "production") -> Optional[Dict[str, Any]]:
    nid = str(node_id or "").strip()
    if not nid:
        return None
    for item in _load_nodes():
        if isinstance(item, dict) and str(item.get("id") or "").strip() == nid:
            return item

    pid = str(project_id or "").strip()
    ctx = _resolve_topology_context(pid, _normalize_env_key(env_key) or "production", "")
    topo = ctx.get("topology") if isinstance(ctx.get("topology"), dict) else {}
    row = ctx.get("row") if isinstance(ctx.get("row"), dict) else {}
    tid = str(row.get("topology_id") or "")
    lookup_id = _DEMO_TO_RUNTIME_NODE.get(nid, nid)
    topo_node = next(
        (
            n for n in (topo.get("nodes") or [])
            if isinstance(n, dict) and str(n.get("id") or "").strip() == lookup_id
        ),
        None,
    )
    if not isinstance(topo_node, dict):
        return None
    built = _build_runtime_node_from_topology_node(pid, env_key, topo_node, tid)
    built["ops_base_url"] = _topology_ops_dispatch_base(pid, env_key, topo)
    built["enabled"] = True
    return _normalize_node(built)


def _resolve_flow_test_node(payload: Dict[str, Any], node_id: str = "") -> Optional[Dict[str, Any]]:
    project_id = str((payload or {}).get("project_id") or "").strip()
    env_key = _normalize_env_key((payload or {}).get("env_key") or "production")
    nid = str(node_id or (payload or {}).get("node_id") or "").strip()
    if not nid:
        return None
    if project_id:
        hit = _resolve_ops_dispatch_node(project_id, nid, env_key)
        if hit:
            return hit
    return _resolve_node(
        node_id=nid,
        project_id=project_id,
        env=str((payload or {}).get("env") or "").strip(),
        channel=str((payload or {}).get("channel") or "").strip(),
    )


def _auto_approve_ops_request(req: Dict[str, Any], node: Dict[str, Any], validation: Dict[str, Any], actor: str, note: str) -> Dict[str, Any]:
    if not validation.get("require_approval") or validation.get("approved"):
        return validation
    aid = create_approval(
        "gm_ops_action",
        actor,
        "ops_action",
        str(validation.get("approval_target_id") or ""),
        reason=str(validation.get("reason") or note),
        project_id=str(node.get("project_id") or ""),
    )
    ok, err = approve_or_reject(aid, actor, "approve", note)
    if not ok:
        validation = dict(validation)
        validation["ok"] = False
        validation["missing"] = list(validation.get("missing") or []) + ["approval_failed"]
        validation["approval_error"] = str(err or "approval failed")
        return validation
    req["approval_id"] = aid
    return _validate_ops_request(req, node)
