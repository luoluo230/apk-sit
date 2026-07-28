# -*- coding: utf-8 -*-
"""Extract ops/helpers.py into domain modules. Plan P1-01."""

from __future__ import annotations

import ast
import os
import re
import textwrap

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
HELPERS = os.path.join(ROOT, "services", "ops", "helpers.py")
OUT_DIR = os.path.join(ROOT, "services", "ops")

MODULE_ORDER = (
    "diagnostics",
    "topology_contracts",
    "cluster_importer",
    "topology_registry",
    "agent_registry",
    "runtime_orchestrator",
)

# Explicit function → module (highest priority)
EXPLICIT: dict[str, str] = {
    "_diagnostics_fix_actions": "diagnostics",
    "_build_diagnostics_summary": "diagnostics",
    "_build_overview": "diagnostics",
    "_build_node_onboarding": "diagnostics",
    "_runtime_active_for_scope": "runtime_orchestrator",
}

# Prefix → module (first match wins)
PREFIX_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("cluster_importer", (
        "_load_cluster_json", "_sync_cluster_to_", "_build_cluster_topology",
        "_cluster_node_", "_cluster_topology_role", "_gameserver_repo",
        "_resolve_game_server_repo", "_gomeku_mongo_dbpath",
    )),
    ("topology_contracts", (
        "_node_contract", "_load_node_contract", "_format_contract_command",
        "_resolve_node_contract", "_contract_daemon", "_cluster_type_for",
        "_cluster_category_for", "_resolve_topology_node_port", "_cluster_relay_port",
        "_cluster_relay_token", "_enrich_cluster_relay", "_build_daemon_metadata",
        "_validate_topology_contract", "_topology_to_cluster_payload",
        "_resolve_env_profile_name",
    )),
    ("diagnostics", (
        "_diagnostics_", "_build_diagnostics_summary", "_build_overview",
        "_build_node_onboarding", "_list_action_targets", "_resolve_action_target",
        "_action_target_or_400", "_load_change_freeze", "_change_freeze",
        "_save_change_freeze", "_build_alerts_from_nodes", "_validate_ops_request",
        "_execute_ops_action", "_execute_validated", "_approval_target_id",
        "_approved_by_id", "_append_bounded", "_append_trace", "_append_event",
        "_find_trace", "_value_contains_token",
    )),
    ("agent_registry", (
        "_normalize_agent_descriptor", "_agents_v2", "_ensure_canonical_local",
        "_upsert_agents", "_consolidate_runtime_agents", "_realtime_metric",
        "_append_realtime_agent", "_ensure_agent_metrics", "_apply_service_metrics",
        "_services_for_project", "_enqueue_agent", "_reconcile_agent",
        "_desired_agent_upgrade", "_auth_agent", "_agent_token", "_agent_status",
        "_agent_managed", "_job_desired", "_job_matches", "_idempotency_key",
        "_member_registration", "_effective_runtime_status", "_extract_control_metrics",
        "_status_rank", "_parse_iso_ts", "_parse_iso_datetime", "_latest_realtime_metric",
        "_overlay_live", "_inject_live", "_sample_local_control", "_load_agent_registry",
        "_save_agent_registry", "_normalize_agent", "_service_dict_from_agent",
        "_service_dict_from_topology", "_is_design_demo_agent",
        "_mark_duplicate_runtime_agents", "_pick_primary_agent", "_logical_agents_for_project",
        "_resolve_agent_from_node", "_device_metrics_snapshot", "_build_agent_metric_series",
        "_build_agent_detail", "_parse_agent_detail_include", "_agent_detail_include_wants",
        "_item_matches_agent_scope",
    )),
    ("runtime_orchestrator", (
        "_runtime_", "_probe_", "_sse_", "_tcp_probe", "_udp_probe", "_redis_",
        "_fetch_cluster_runtime", "_invalidate_runtime_probe", "_seed_probe_cache",
        "_derive_agent_probe", "_merge_probe_with", "_business_test", "_run_business_test",
        "_orchestrate_", "_wait_agent", "_wait_topology", "_spawn_runtime",
        "_topo_order_node", "_refresh_runtime_service", "_ensure_runtime_infra_ports",
        "_runtime_run_patch", "_runtime_orchestrator", "_count_gameserver",
        "_ws_handshake", "_biz_", "_cancel_runtime", "_mark_project_runtime",
        "_service_starting_grace", "_resolve_service_runtime", "_resolve_bound_agent",
        "_resolve_agent_probe", "_resolve_runtime_probe", "_resolve_orchestration",
        "_is_embedded_", "_is_daemon_infra", "_default_probe_host",
        "_is_local_runtime_agent", "_cluster_state_is_online",
        "_build_sse_payload", "_ensure_probe_bg_started", "_probe_bg_loop",
        "_orchestration_post_launch_wait", "_normalize_business_steps",
        "_resolve_business_test_gateway_endpoint", "_summarize_business_test_failure",
        "_load_daemon_state", "_save_daemon_state", "_set_daemon_state", "_get_daemon_state",
        "_is_process_running", "_daemon_log_path", "_gameserver_log_artifact_paths",
        "_is_gameserver_process", "_find_gameserver_pid", "_gameserver_service",
        "_embedded_process_gateway_up", "_service_runtime_cache_fresh",
        "_should_use_cached_service_state",
    )),
    ("topology_registry", (
        "_topology", "_list_topologies", "_ensure_topology", "_load_topology_scoped",
        "_save_topology_scoped", "_resolve_topology", "_migrate_topology",
        "_normalize_topology", "_purge_design_demo", "_ensure_design",
        "_design_reference", "_project_has_cluster", "_topology_has",
        "_ensure_runtime_topology", "_topology_missing", "_build_runtime_infra",
        "_append_runtime_infra", "_apply_runtime_minimal", "_migrate_gomeku",
        "_core_minimal_topology", "_project_uses_runtime", "_purge_design_demo_project",
        "_resolve_flow_test", "_smoke_probe_topology", "_auto_approve_ops",
        "_needs_design_reference", "_ensure_design_reference", "_default_topology",
        "_normalize_layout", "_load_scope_", "_save_scope_", "_binding_fallback",
        "_runtime_default_topology", "_sync_topology_to_game", "_repair_runtime_topology",
        "_strip_default_node", "_build_runtime_node", "_resolve_ops_dispatch",
        "_resolve_topology_node_id", "_resolve_ops_project", "_resolve_ops_env",
        "_resolve_ops_topology", "_ops_platform_redirect", "_agent_matches_env",
        "_ops_structured", "_can_reach_without", "_is_critical_topology",
        "_ops_ensure_free_port", "_ensure_topology_for_scope",
        "_normalize_node", "_default_nodes", "_repair_legacy_node_text", "_load_nodes",
        "_save_nodes", "_resolve_node", "_node_or_400", "_load_topology", "_save_topology",
        "_is_design_demo_topology_row", "_resolve_scope_agent_bindings_for_scope",
        "_resolve_scope_service_bindings_for_scope", "_enrich_preset_from_contract",
        "_default_node_presets", "_load_node_presets", "_preset_role_rules",
        "_connect_rule_meta", "_link_role_block_reason", "_can_link_nodes",
        "_infer_node_kind", "_default_ports_for_kind", "_normalize_ports",
        "_gateway_blueprint_ports", "_commercial_framework_core_edges",
        "_normalize_blueprint_edge_rel", "_blueprint_edge_instance_pairs",
        "_apply_topology_blueprint_edges", "_layout_blueprint_nodes_by_layer",
        "_merge_topology_blueprints_with_defaults", "_load_topology_blueprints",
        "_is_external_daemon_node",
    )),
]

FACADE_KEEP = {
    "_session_username",
    "_allow_ops_view",
    "_allow_ops_execute",
    "_allow_gm_execute",
    "_ops_csrf_token",
    "_render_ops_page",
    "_render_page",
    "_render_local_template",
    "_render_standalone_page",
}

HEADER = '''# -*- coding: utf-8 -*-
"""{doc}"""

from __future__ import annotations

'''


def classify(name: str) -> str:
    if name in EXPLICIT:
        return EXPLICIT[name]
    if name in FACADE_KEEP:
        return "facade"
    for module, prefixes in PREFIX_RULES:
        for prefix in prefixes:
            if name.startswith(prefix) or name == prefix.rstrip("_"):
                return module
    return "topology_registry"


def extract_segments(source: str, tree: ast.Module) -> tuple[dict[str, list[str]], dict[str, list[str]]]:
    lines = source.splitlines(keepends=True)
    func_chunks: dict[str, list[str]] = {m: [] for m in MODULE_ORDER}
    func_chunks["facade"] = []
    assign_chunks: dict[str, list[str]] = {m: [] for m in MODULE_ORDER}
    assign_chunks["facade"] = []

    for node in tree.body:
        if isinstance(node, ast.FunctionDef):
            mod = classify(node.name)
            chunk = lines[node.lineno - 1 : node.end_lineno]
            func_chunks[mod].append("".join(chunk))
        elif isinstance(node, ast.Assign):
            # module-level assigns: keep imports/constants in facade unless cluster-specific
            text = "".join(lines[node.lineno - 1 : node.end_lineno])
            target_names = []
            for t in node.targets:
                if isinstance(t, ast.Name):
                    target_names.append(t.id)
            mod = "facade"
            for name in target_names:
                if name == "CLUSTER_JSON_PATH" or name.startswith("_probe_") or name.startswith("_sse_"):
                    mod = "runtime_orchestrator"
                elif name.startswith("_NODE_CONTRACT"):
                    mod = "topology_contracts"
            assign_chunks[mod].append(text)
        elif isinstance(node, (ast.Import, ast.ImportFrom)):
            pass  # handled separately
        elif isinstance(node, ast.For):
            # re-export loop at top — skip
            text = "".join(lines[node.lineno - 1 : node.end_lineno])
            if "globals()" in text:
                continue
            assign_chunks["facade"].append(text)
        elif isinstance(node, ast.If):
            text = "".join(lines[node.lineno - 1 : node.end_lineno])
            if node.lineno < 120:
                assign_chunks["facade"].append(text)

    return func_chunks, assign_chunks


def collect_import_block(source: str, tree: ast.Module) -> str:
    lines = source.splitlines(keepends=True)
    parts: list[str] = []
    for node in tree.body:
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            parts.append("".join(lines[node.lineno - 1 : node.end_lineno]))
        elif isinstance(node, ast.Assign) and node.lineno < 120:
            continue
        elif isinstance(node, ast.FunctionDef):
            break
    # Also grab lines 82-121 globals (client, probe cache) — include in runtime
    return "".join(parts)


def write_module(name: str, doc: str, import_block: str, assigns: list[str], funcs: list[str]) -> None:
    if name == "facade":
        return
    if not funcs and not assigns:
        return
    path = os.path.join(OUT_DIR, f"{name}.py")
    body = HEADER.format(doc=doc)
    body += import_block
    body += "\n\n"
    if assigns:
        body += "".join(assigns)
        if not body.endswith("\n\n"):
            body += "\n"
    body += "\n".join(funcs)
    if not body.endswith("\n"):
        body += "\n"
    with open(path, "w", encoding="utf-8") as fp:
        fp.write(body)
    print(f"wrote {path} ({len(funcs)} funcs, {sum(1 for _ in open(path, encoding='utf-8'))} lines)")


def build_facade(func_chunks: dict[str, list[str]], import_block: str, assigns: list[str]) -> str:
    lines = [
        '# -*- coding: utf-8 -*-',
        '"""Ops platform thin facade — re-exports domain modules. Plan P1-01."""',
        "",
        "from __future__ import annotations",
        "",
    ]
    lines.append(import_block.strip())
    lines.append("")
    lines.append("from services.ops.runtime_service import _runtime_active_for_scope")
    lines.append("from services.ops.topology_service import (")
    lines.append("    _default_env_options, _env_label, _load_topology_contents,")
    lines.append("    _load_topology_registry, _normalize_env_key, _save_topology_contents,")
    lines.append("    _save_topology_registry, _scope_binding_key, _topology_content_counts,")
    lines.append(")")
    lines.append("from services.ops.agent_service import _default_agent_policy, _load_agent_policy, _save_agent_policy")
    lines.append("")
    for mod in MODULE_ORDER:
        lines.append(f"from services.ops.{mod} import *  # noqa: F403")
    lines.append("")
    lines.append("# Auth + page render (facade-only)")
    if func_chunks.get("facade"):
        lines.append("".join(func_chunks.get("facade", [])))
    if assigns:
        lines.append("".join(assigns))
    lines.append("")
    lines.append("__all__ = []  # wildcard re-exports preserve backward compat")
    return "\n".join(lines) + "\n"


def main() -> int:
    with open(HELPERS, encoding="utf-8") as fp:
        source = fp.read()
    tree = ast.parse(source)
    import_block = collect_import_block(source, tree)
    func_chunks, assign_chunks = extract_segments(source, tree)

    docs = {
        "diagnostics": "Ops diagnostics summaries and onboarding views.",
        "topology_contracts": "Node contract registry, ports, and daemon commands.",
        "cluster_importer": "cluster.json import and sync to agents/topology.",
        "topology_registry": "Topology CRUD, scoped load/save, bindings.",
        "agent_registry": "Agent registry merge, heartbeat, and stale handling.",
        "runtime_orchestrator": "Runtime start/stop orchestration and probes.",
    }

    backup = HELPERS + ".bak"
    if not os.path.isfile(backup):
        with open(backup, "w", encoding="utf-8") as fp:
            fp.write(source)
        print(f"backup -> {backup}")

    for mod in MODULE_ORDER:
        write_module(mod, docs[mod], import_block, assign_chunks.get(mod, []), func_chunks.get(mod, []))

    facade_src = build_facade(func_chunks, import_block, assign_chunks.get("facade", []))
    with open(HELPERS, "w", encoding="utf-8") as fp:
        fp.write(facade_src)
    print(f"facade lines: {sum(1 for _ in open(HELPERS, encoding='utf-8'))}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
