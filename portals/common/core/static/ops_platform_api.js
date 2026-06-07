(function(){
  const api = {};
  api.domain = {
    entities: ['Node','Edge','Action','Task','Approval','Event','Trace','Agent','Policy'],
    actionStates: ['draft','pending_approval','queued','leased','running','success','failed','timeout','canceled'],
    nodeHealth: ['healthy','degraded','offline','unknown'],
    riskLevels: ['low','medium','high','critical']
  };

  const ERROR_MAP = {
    'invalid_edge_by_role': { code:'OPS_EDGE_ROLE_FORBIDDEN', level:'warn', message:'当前节点角色关系不允许该连线' },
    'invalid edge endpoints': { code:'OPS_EDGE_ENDPOINT_INVALID', level:'error', message:'连线起点或终点无效' },
    'node not found': { code:'OPS_NODE_NOT_FOUND', level:'error', message:'节点不存在或已被删除' },
    'missing edge_id': { code:'OPS_EDGE_ID_MISSING', level:'error', message:'缺少连线标识' },
    'edge not found': { code:'OPS_EDGE_NOT_FOUND', level:'warn', message:'连线不存在或已删除' },
    'forbidden': { code:'OPS_FORBIDDEN', level:'error', message:'权限不足，无法执行当前操作' },
    'port_not_found': { code:'OPS_PORT_NOT_FOUND', level:'error', message:'端口不存在或已变更' },
    'port_capacity_exceeded': { code:'OPS_PORT_CAPACITY_EXCEEDED', level:'warn', message:'端口连接数已达上限' },
    'edge_duplicate': { code:'OPS_EDGE_DUPLICATE', level:'warn', message:'重复连线' },
    'edge_delete_blocked': { code:'OPS_EDGE_DELETE_BLOCKED', level:'warn', message:'关键链路连线不可删除' },
    'node_kind_violation': { code:'OPS_NODE_KIND_VIOLATION', level:'warn', message:'节点类型不允许该方向连线' },
    'node_delete_blocked': { code:'OPS_NODE_DELETE_BLOCKED', level:'warn', message:'该节点为关键节点，删除会破坏当前链路' }
  };

  function normalizeError(payload, status){
    const raw = (payload && (payload.error || payload.message)) ? String(payload.error || payload.message) : '';
    const mapped = ERROR_MAP[raw] || null;
    const code = mapped ? mapped.code : (payload && payload.error_code ? String(payload.error_code) : (status===0?'OPS_NETWORK_ERROR':'OPS_UNKNOWN_ERROR'));
    return {
      ok:false,
      error: raw || 'request_failed',
      error_code: code,
      level: mapped ? mapped.level : (status>=500?'error':'warn'),
      message: (payload && payload.message) || (mapped && mapped.message) || raw || '请求失败',
      _http_status: status || 0,
      _raw: payload || null
    };
  }

  async function requestJSON(url, options){
    try{
      const r = await fetch(url, options || {});
      const ct = String(r.headers.get('content-type') || '').toLowerCase();
      let data = {};
      if(ct.indexOf('application/json') >= 0){
        try{ data = await r.json(); }catch(_){ data = {}; }
      }else{
        const text = await r.text();
        const looksHtml = /<html|<!doctype/i.test(String(text || '').slice(0, 200));
        if(looksHtml){
          if(r.status === 401 || r.status === 302 || /login/i.test(String(r.url || ''))){
            return {
              ok:false,
              error:'auth_redirect',
              error_code:'OPS_AUTH_REQUIRED',
              level:'error',
              message:'登录态已失效，请重新登录后重试',
              _http_status:r.status || 200
            };
          }
          if(r.status === 403){
            return {
              ok:false,
              error:'forbidden',
              error_code:'OPS_FORBIDDEN',
              level:'error',
              message:'权限不足，无法执行当前操作',
              _http_status:r.status || 403
            };
          }
          if(r.status === 404){
            return {
              ok:false,
              error:'not_found',
              error_code:'OPS_NOT_FOUND',
              level:'warn',
              message:'目标资源不存在',
              _http_status:r.status || 404
            };
          }
          if(r.status >= 500){
            return {
              ok:false,
              error:'server_error',
              error_code:'OPS_SERVER_ERROR',
              level:'error',
              message:'服务异常，请稍后重试',
              _http_status:r.status || 500
            };
          }
          return {
            ok:false,
            error:'auth_redirect',
            error_code:'OPS_AUTH_REQUIRED',
            level:'warn',
            message:'接口返回了非 JSON 页面响应',
            _http_status:r.status || 200
          };
        }
        return {
          ok:false,
          error:'non_json_response',
          error_code:'OPS_API_NON_JSON',
          level:'error',
          message:'接口返回格式异常（非 JSON）',
          _http_status:r.status || 200
        };
      }
      if(!r.ok || (data && data.ok===false)){
        return Object.assign({}, data || {}, normalizeError(data, r.status));
      }
      if(data && typeof data==='object') return Object.assign({_http_status:r.status}, data);
      return {ok:true, data:data, _http_status:r.status};
    }catch(err){
      return normalizeError({error:String((err&&err.message)||'network_error')}, 0);
    }
  }

  api.getJSON = async (url) => requestJSON(url);
  api.postJSON = async (url, body) => requestJSON(url, {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body||{})});

  api.mapError = (payload) => normalizeError(payload || {}, Number((payload||{})._http_status)||0);

  api.logClientEvent = (eventName, payload) => api.postJSON('/api/ops-platform/client-log', {event:eventName, payload:payload||{}});

  api.loadNodes = () => api.getJSON('/api/gm-legacy/nodes');
  function withScope(base, scope){
    const q = [];
    const s = scope || {};
    if (s.project_id || s.projectId) q.push('project_id=' + encodeURIComponent(s.project_id || s.projectId));
    if (s.env_key || s.envKey) q.push('env_key=' + encodeURIComponent(s.env_key || s.envKey));
    if (s.topology_id || s.topologyId) q.push('topology_id=' + encodeURIComponent(s.topology_id || s.topologyId));
    return base + (q.length ? ('?' + q.join('&')) : '');
  }
  api.loadOverview = (projectId) => api.getJSON('/api/ops-platform/overview' + (projectId ? ('?project_id='+encodeURIComponent(projectId)) : ''));
  api.loadProjects = (status) => api.getJSON('/api/projects' + (status ? ('?status=' + encodeURIComponent(status)) : ''));
  api.loadTopologies = (scope) => api.getJSON(withScope('/api/ops-platform/topologies', scope));
  api.loadTopologyDetail = (scope) => api.getJSON(withScope('/api/ops-platform/topologies/detail', scope));
  api.createTopology = (payload) => api.postJSON('/api/ops-platform/topologies/create', payload || {});
  api.copyTopology = (payload) => api.postJSON('/api/ops-platform/topologies/copy', payload || {});
  api.setDefaultTopology = (payload) => api.postJSON('/api/ops-platform/topologies/set-default', payload || {});
  api.deleteTopology = (payload) => api.postJSON('/api/ops-platform/topologies/delete', payload || {});
  api.loadTopology = (scope) => api.getJSON(withScope('/api/ops-platform/topology', scope));
  api.loadPresets = () => api.getJSON('/api/ops-platform/node-presets');
  api.loadTopologyBlueprints = () => api.getJSON('/api/ops-platform/topology-blueprints');
  api.applyTopologyBlueprint = (payload) => api.postJSON('/api/ops-platform/topology/apply-blueprint', payload);
  api.loadEvents = (limit) => api.getJSON('/api/ops-platform/events?limit=' + (limit || 80));
  api.loadOnboarding = (projectId) => api.getJSON('/api/ops-platform/node-onboarding' + (projectId ? ('?project_id=' + encodeURIComponent(projectId)) : ''));
  api.loadDiagnosticsSummary = (projectId) => api.getJSON('/api/ops-platform/diagnostics/summary' + (projectId ? ('?project_id=' + encodeURIComponent(projectId)) : ''));
  api.loadActionTargets = (projectId) => api.getJSON('/api/ops-platform/action-targets' + (projectId ? ('?project_id=' + encodeURIComponent(projectId)) : ''));
  api.loadActionCatalog = () => api.getJSON('/api/ops-platform/action-catalog');
  api.validateAction = (payload) => api.postJSON('/api/ops-platform/actions/validate', payload);
  api.executeAction = (payload) => api.postJSON('/api/ops-platform/actions/execute', payload);
  api.createActionApproval = (payload) => api.postJSON('/api/ops-platform/actions/approval', payload);
  api.saveTopology = (payload) => api.postJSON('/api/ops-platform/topology/save', payload || {});
  api.updateNode = (payload) => api.postJSON('/api/ops-platform/topology/node/update', payload || {});
  api.cloneNode = (payload) => api.postJSON('/api/ops-platform/topology/node/clone', payload || {});
  api.disableNode = (payload) => api.postJSON('/api/ops-platform/topology/node/disable', payload || {});
  api.nodeLogs = (scope) => api.getJSON(withScope('/api/ops-platform/topology/node/logs', scope));
  api.deleteNode = (payload) => api.postJSON('/api/ops-platform/topology/node/delete', payload || {});
  api.upsertEdge = (payload) => api.postJSON('/api/ops-platform/topology/edge/upsert', payload || {});
  api.deleteEdge = (payload) => api.postJSON('/api/ops-platform/topology/edge/delete', payload || {});
  api.structuredAddExistingTarget = (payload) => api.postJSON('/api/ops-platform/topology/structured/add-existing-target', payload || {});
  api.structuredAddNewTarget = (payload) => api.postJSON('/api/ops-platform/topology/structured/add-new-target', payload || {});
  api.structuredDeleteNode = (payload) => api.postJSON('/api/ops-platform/topology/structured/delete-node', payload || {});
  api.structuredDeleteEdge = (payload) => api.postJSON('/api/ops-platform/topology/structured/delete-edge', payload || {});
  api.addNodeFromPreset = (payload) => api.postJSON('/api/ops-platform/node/add-from-preset', payload);
  api.queryTrace = (traceId) => api.getJSON('/api/ops-platform/actions/' + encodeURIComponent(traceId));
  api.agentPolicy = () => api.getJSON('/api/ops-platform/agent/policy');
  api.updateAgentPolicy = (payload) => api.postJSON('/api/ops-platform/agent/policy', payload);
  api.agents = (projectId, status, deviceId, bound, hostIp) => {
    const q = [];
    if (projectId) q.push('project_id=' + encodeURIComponent(projectId));
    if (status) q.push('status=' + encodeURIComponent(status));
    if (deviceId) q.push('device_id=' + encodeURIComponent(deviceId));
    if (bound) q.push('bound=' + encodeURIComponent(bound));
    if (hostIp) q.push('host_ip=' + encodeURIComponent(hostIp));
    return api.getJSON('/api/ops-platform/agents' + (q.length ? ('?' + q.join('&')) : ''));
  };
  api.agentDevices = (projectId) => api.getJSON('/api/ops-platform/agents/devices' + (projectId ? ('?project_id=' + encodeURIComponent(projectId)) : ''));
  api.upsertAgent = (payload) => api.postJSON('/api/ops-platform/agents/upsert', payload);
  api.cleanupExpiredAgents = (payload) => api.postJSON('/api/ops-platform/agents/cleanup-expired', payload || {});
  api.probeAgent = (payload) => api.postJSON('/api/ops-platform/agents/probe', payload || {});
  api.restartAgent = (payload) => api.postJSON('/api/ops-platform/agents/restart', payload || {});
  api.probeAllAgents = (payload) => api.postJSON('/api/ops-platform/agents/probe-all', payload || {});
  api.probeRepairAgents = (payload) => api.postJSON('/api/ops-platform/agents/probe-repair', payload || {});
  api.syncCluster = (payload) => api.postJSON('/api/ops-platform/cluster/sync', payload || {});
  api.startRemoteNode = (payload) => api.postJSON('/api/ops-platform/topology/node/start-remote', payload || {});
  api.loadNodeBindings = (scope) => api.getJSON(withScope('/api/ops-platform/topology/node/bindings', scope));
  api.bindNodeAgent = (payload) => api.postJSON('/api/ops-platform/topology/node/bind-agent', payload);
  api.bindNodeService = (payload) => api.postJSON('/api/ops-platform/topology/node/bind-service', payload);
  api.listServices = (projectId) => api.getJSON('/api/ops-platform/services' + (projectId ? ('?project_id=' + encodeURIComponent(projectId)) : ''));
  api.upsertService = (payload) => api.postJSON('/api/ops-platform/services/upsert', payload || {});
  api.serviceAction = (payload) => api.postJSON('/api/ops-platform/services/action', payload || {});
  api.serviceLogs = (params) => {
    const q = [];
    const p = params || {};
    if (p.project_id || p.projectId) q.push('project_id=' + encodeURIComponent(p.project_id || p.projectId));
    if (p.service_id || p.serviceId) q.push('service_id=' + encodeURIComponent(p.service_id || p.serviceId));
    if (p.level) q.push('level=' + encodeURIComponent(p.level));
    if (p.q) q.push('q=' + encodeURIComponent(p.q));
    if (p.tail) q.push('tail=' + encodeURIComponent(p.tail));
    if (p.since_offset != null) q.push('since_offset=' + encodeURIComponent(p.since_offset));
    if (p.current_session != null) q.push('current_session=' + encodeURIComponent(p.current_session));
    if (p.hide_lifecycle != null) q.push('hide_lifecycle=' + encodeURIComponent(p.hide_lifecycle));
    return api.getJSON('/api/ops-platform/services/logs' + (q.length ? ('?' + q.join('&')) : ''));
  };
  api.autoBindAgents = (payload) => api.postJSON('/api/ops-platform/topology/auto-bind-agents', payload || {});
  api.agentJobs = (nodeId, status, limit) => {
    const q = [];
    if (nodeId) q.push('node_id=' + encodeURIComponent(nodeId));
    if (status) q.push('status=' + encodeURIComponent(status));
    if (limit) q.push('limit=' + encodeURIComponent(limit));
    return api.getJSON('/api/ops-platform/agent/jobs' + (q.length ? ('?' + q.join('&')) : ''));
  };
  api.agentDetail = (projectId, agentId) => {
    const q = [];
    if (projectId) q.push('project_id=' + encodeURIComponent(projectId));
    if (agentId) q.push('agent_id=' + encodeURIComponent(agentId));
    return api.getJSON('/api/ops-platform/agent/detail' + (q.length ? ('?' + q.join('&')) : ''));
  };
  api.agentAudit = (projectId, agentId, limit) => {
    const q = [];
    if (projectId) q.push('project_id=' + encodeURIComponent(projectId));
    if (agentId) q.push('agent_id=' + encodeURIComponent(agentId));
    if (limit) q.push('limit=' + encodeURIComponent(limit));
    return api.getJSON('/api/ops-platform/agent/audit' + (q.length ? ('?' + q.join('&')) : ''));
  };
  api.controlPlaneSummary = () => api.getJSON('/api/ops-platform/control-plane/summary');
  api.changeGovernanceSummary = (projectId) => api.getJSON('/api/ops-platform/change-governance/summary' + (projectId ? ('?project_id=' + encodeURIComponent(projectId)) : ''));
  api.setChangeFreeze = (payload) => api.postJSON('/api/ops-platform/change-governance/freeze', payload || {});
  api.moduleMap = () => api.getJSON('/api/ops-platform/module-map');
  api.runtimeFlowControl = (payload) => api.postJSON('/api/ops-platform/runtime/flow-control', payload || {});
  api.runtimeFlowStatus = (runId) => api.getJSON('/api/ops-platform/runtime/flow-status?run_id=' + encodeURIComponent(runId || ''));
  api.runtimeFlowActive = (scope) => api.getJSON(withScope('/api/ops-platform/runtime/active', scope));
  api.saveWorkbenchMode = (payload) => api.postJSON('/api/ops-platform/topology/workbench-mode', payload || {});

  window.OpsApi = api;
})();
