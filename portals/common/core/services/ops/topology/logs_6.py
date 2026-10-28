def _is_critical_topology_node(topo: Dict[str, Any], node_id: str) -> bool:
    nodes = [x for x in (topo.get("nodes") or []) if isinstance(x, dict)]
    edges = [x for x in (topo.get("edges") or []) if isinstance(x, dict)]
    target = None
    for n in nodes:
        if str(n.get("id") or "") == node_id:
            target = n
            break
    if not target:
        return False

    kind = str(target.get("kind") or "standard")
    linked_edges = [e for e in edges if str(e.get("from") or "") == node_id or str(e.get("to") or "") == node_id]
    if not linked_edges:
        return False

    if kind == "entry":
        other_entry = [n for n in nodes if str(n.get("id") or "") != node_id and str(n.get("kind") or "") == "entry"]
        if not other_entry:
            return True
    if kind == "terminal":
        other_terminal = [n for n in nodes if str(n.get("id") or "") != node_id and str(n.get("kind") or "") == "terminal"]
        if not other_terminal:
            return True

    incoming = list({str(e.get("from") or "") for e in edges if str(e.get("to") or "") == node_id})
    outgoing = list({str(e.get("to") or "") for e in edges if str(e.get("from") or "") == node_id})
    incoming = [x for x in incoming if x]
    outgoing = [x for x in outgoing if x]
    if incoming and outgoing:
        for s in incoming:
            for t in outgoing:
                if not _can_reach_without_node(edges, s, t, node_id):
                    return True
    return False


def _is_critical_topology_edge(topo: Dict[str, Any], edge_id: str) -> bool:
    nodes = [x for x in (topo.get("nodes") or []) if isinstance(x, dict)]
    edges = [x for x in (topo.get("edges") or []) if isinstance(x, dict)]
    if not nodes or not edges:
        return False
    target = None
    for e in edges:
        if str(e.get("id") or "") == edge_id:
            target = e
            break
    if not target:
        return False

    entry_ids = [str(n.get("id") or "") for n in nodes if str(n.get("kind") or "") == "entry"]
    term_ids = [str(n.get("id") or "") for n in nodes if str(n.get("kind") or "") == "terminal"]
    if not entry_ids or not term_ids:
        return False

    def _reachable(edge_rows: List[Dict[str, Any]], roots: List[str]) -> set:
        graph: Dict[str, List[str]] = {}
        for e in edge_rows:
            a = str(e.get("from") or "")
            b = str(e.get("to") or "")
            if not a or not b:
                continue
            graph.setdefault(a, []).append(b)
        seen = set(roots)
        queue = list(roots)
        while queue:
            cur = queue.pop(0)
            for nxt in graph.get(cur, []):
                if nxt in seen:
                    continue
                seen.add(nxt)
                queue.append(nxt)
        return seen

    before = _reachable(edges, entry_ids)
    after = _reachable([e for e in edges if str(e.get("id") or "") != edge_id], entry_ids)
    for tid in term_ids:
        if tid in before and tid not in after:
            return True
    return False
