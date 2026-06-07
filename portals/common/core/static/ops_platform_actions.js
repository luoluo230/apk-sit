(function(){
  const $=(id)=>document.getElementById(id);
  const esc=(v)=>String(v==null?'':v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const state={projectId:'', jobStatus:'', targets:[], catalog:[]};
  const GROUP_ZH={
    observe:'观测巡检',
    lifecycle:'生命周期',
    incident:'故障处置',
    operation:'运维控制',
    special:'专项作业'
  };
  const ACTION_ZH={
    health_check:'健康检查',
    ready_check:'就绪检查',
    status:'运行快照',
    runtime_snapshot:'运行态详情',
    log_tail:'日志尾部',
    start:'启动',
    stop:'停止',
    restart:'重启',
    start_all:'全量启动',
    stop_all:'全量停止',
    smoke_test:'冒烟测试',
    stress_test:'压力测试'
  };

  function statusBadge(status){
    const s=String(status||'').toUpperCase();
    const cls=(s==='ONLINE'||s==='SUCCESS'||s==='PASS')?'state-ok':((s==='RUNNING'||s==='PENDING'||s==='DEGRADED')?'state-warn':'state-err');
    return '<span class="state-pill '+cls+'">'+esc(s||'-')+'</span>';
  }

  function selectedTarget(){
    const key=String(($('actTargetKey')||{}).value||'').trim();
    return state.targets.find(t=>String(t.target_key||'')===key)||null;
  }

  function renderTargetOptions(filterType){
    const ft=String(filterType||'').trim();
    const list=state.targets.filter(t=>!ft||String(t.target_type||'')===ft);
    const sel=$('actTargetKey');
    if(!sel) return;
    const cur=sel.value;
    sel.innerHTML=list.map(t=>'<option value="'+esc(t.target_key)+'" data-type="'+esc(t.target_type)+'">'+esc(t.label||t.target_key)+'</option>').join('');
    if(cur && list.some(t=>t.target_key===cur)) sel.value=cur;
    else if(list.length) sel.value=list[0].target_key;
    syncTargetMeta();
  }

  function syncTargetMeta(){
    const t=selectedTarget();
    const meta=$('actTargetMeta');
    if(!meta) return;
    if(!t){ meta.textContent='未选择目标'; return; }
    meta.innerHTML='类型='+esc(t.target_type)+' | node='+esc(t.node_id||'-')+' | agent='+esc(t.agent_id||'-')+' | probe='+statusBadge(t.probe_status||'-');
    if($('actTarget') && !$('actTarget').value) $('actTarget').value=String(t.service_id||t.node_id||'');
  }

  function renderCatalog(){
    const actions=state.catalog||[];
    if(!actions.length){
      $('actType').innerHTML='<option value="">暂无可用动作</option>';
      return;
    }
    const byGroup={};
    actions.forEach(a=>{
      const gid=String(a.groupId||a.group_id||'other');
      if(!byGroup[gid]) byGroup[gid]=[];
      byGroup[gid].push(a);
    });
    $('actType').innerHTML=Object.keys(byGroup).map(gid=>{
      const first=byGroup[gid][0]||{};
      const opts=byGroup[gid].map(a=>{
        const val=String(a.value||a.action||a.action_type||'');
        const label=ACTION_ZH[val]||a.label||val;
        const risk=String(a.risk||'low');
        return '<option value="'+esc(val)+'" data-risk="'+esc(risk)+'">'+esc(label)+'</option>';
      }).join('');
      return '<optgroup label="'+esc(GROUP_ZH[gid]||first.group||gid)+'">'+opts+'</optgroup>';
    }).join('');
  }

  function buildRequest(extra){
    const t=selectedTarget();
    const req={
      project_id:state.projectId,
      target_key:String(($('actTargetKey')||{}).value||''),
      target_type:t?String(t.target_type||''):String(($('actTargetType')||{}).value||''),
      node_id:t?String(t.node_id||''):'',
      service_id:t?String(t.service_id||''):'',
      agent_id:t?String(t.agent_id||''):'',
      action_type:$('actType').value,
      target:$('actTarget').value,
      reason:$('actReason').value,
      ticket_id:$('actTicket')?$('actTicket').value:'',
      approver:$('actApprover')?$('actApprover').value:'',
      via_agent:true,
      run_mode:'agent'
    };
    return Object.assign(req, extra||{});
  }

  async function loadBasics(){
    const [targetsResp,catalog,events]=await Promise.all([
      OpsApi.loadActionTargets(state.projectId),
      OpsApi.loadActionCatalog(),
      OpsApi.loadEvents(30)
    ]);
    state.targets=(targetsResp&&targetsResp.targets)||[];
    state.catalog=(catalog.actions||catalog.catalog||catalog.data||[]);
    renderTargetOptions(($('actTargetType')||{}).value||'');
    renderCatalog();
    applyUrlPrefill();
    const list=$('execEvents'); list.innerHTML='';
    (events.events||[]).slice(0,12).forEach(it=>{
      const row=document.createElement('div');
      row.style.cssText='border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:8px';
      row.innerHTML='<div style="display:flex;justify-content:space-between"><b>'+esc(it.action||it.type||'-')+'</b><span style="font-size:11px;color:#64748b">'+esc(it.level||'info')+'</span></div><div style="font-size:11px;color:#64748b">'+esc(it.message||'')+'</div>';
      list.appendChild(row);
    });
  }

  function applyUrlPrefill(){
    const qs=new URLSearchParams(window.location.search);
    const tk=String(qs.get('target_key')||'').trim();
    const at=String(qs.get('action_type')||'').trim();
    const tt=String(qs.get('target_type')||'').trim();
    if(tt && $('actTargetType')){ $('actTargetType').value=tt; renderTargetOptions(tt); }
    if(tk && $('actTargetKey')) $('actTargetKey').value=tk;
    if(at && $('actType')) $('actType').value=at;
    syncTargetMeta();
  }

  async function run(mode){
    const req=buildRequest();
    const d=mode==='validate'?await OpsApi.validateAction(req):(mode==='approval'?await OpsApi.createActionApproval(req):await OpsApi.executeAction(req));
    $('execOutput').textContent=JSON.stringify(d,null,2);
    $('execMeta').textContent=(d.ok?'成功: ':'失败: ')+(d.message||d.error||mode)+(d.trace_id?(' | trace='+d.trace_id):'')+(d.approval_id?(' | approval='+d.approval_id):'');
    if(mode==='execute' && d.ok) await loadAgentRegistryAndQueue();
  }

  function parseBool(v){return String(v)==='true'||v===true;}
  function toNum(v,d){const n=Number(v);return Number.isFinite(n)?n:d;}

  async function loadPolicy(){
    const d=await OpsApi.agentPolicy();
    const p=(d&&d.policy)||{};
    const r=(p.rollout&&typeof p.rollout==='object')?p.rollout:{};
    $('polMtls').value=String(!!p.mtls_required);
    $('polConc').value=String(p.default_node_concurrency??1);
    $('polLease').value=String(p.lease_timeout_sec??60);
    $('polRetry').value=String(p.max_retries??2);
    $('polRollEnable').value=String(!!r.enabled);
    $('polVersion').value=String(r.desired_version||'');
    $('polChannel').value=String(r.channel||'stable');
    $('polPercent').value=String(r.percent??0);
    $('polAllowIds').value=Array.isArray(r.allow_ids)?r.allow_ids.join(','):'';
  }

  async function savePolicy(){
    const payload={
      mtls_required: parseBool($('polMtls').value),
      default_node_concurrency: Math.max(1, Math.min(20, toNum($('polConc').value,1))),
      lease_timeout_sec: Math.max(5, Math.min(3600, toNum($('polLease').value,60))),
      max_retries: Math.max(0, Math.min(10, toNum($('polRetry').value,2))),
      rollout:{
        enabled: parseBool($('polRollEnable').value),
        desired_version: String($('polVersion').value||'').trim(),
        channel: String($('polChannel').value||'stable').trim()||'stable',
        percent: Math.max(0, Math.min(100, toNum($('polPercent').value,0))),
        allow_ids: String($('polAllowIds').value||'').split(',').map(x=>x.trim()).filter(Boolean)
      }
    };
    const d=await OpsApi.updateAgentPolicy(payload);
    $('execMeta').textContent=(d.ok?'策略已保存':'策略保存失败')+(d.error?(' | '+d.error):'');
    await loadPolicy();
  }

  async function loadAgentRegistryAndQueue(){
    const status=String($('qStatus').value||'').trim();
    const d=await OpsApi.agentJobs('',status,120);
    const jobs=Array.isArray(d.jobs)?d.jobs:[];
    const agents=(d.agents && typeof d.agents==='object')?d.agents:{};
    const regWrap=$('agentRegistryWrap');
    const keys=Object.keys(agents);
    if(!keys.length){regWrap.innerHTML='<div class="preset-empty">暂无 Agent 在线记录</div>';} else {
      regWrap.innerHTML=keys.map(k=>{
        const a=agents[k]||{};
        return '<div style="border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:8px;margin-bottom:8px">'
          +'<div style="display:flex;justify-content:space-between"><b>'+esc(a.agent_id||k)+'</b>'+statusBadge(a.status||'UNKNOWN')+'</div>'
          +'<div style="font-size:11px;color:#64748b">node='+esc(a.node_id||k)+' | ver='+esc(a.version||'-')+' | ip='+esc(a.ip||'-')+'</div>'
          +'<div style="font-size:11px;color:#64748b">last_seen='+esc(a.last_seen||'-')+(a.upgrade_status?(' | upgrade='+esc(a.upgrade_status)):'')+'</div></div>';
      }).join('');
    }

    const c={PENDING:0,RUNNING:0,SUCCESS:0,FAILED:0,CANCELED:0,TIMEOUT:0};
    jobs.forEach(j=>{const s=String(j.status||'').toUpperCase(); if(c[s]!==undefined)c[s]++;});
    $('queueSummary').innerHTML=''
      +'<div style="border:1px solid #dbe6fb;border-radius:8px;padding:8px;background:#fff">Pending: <b>'+c.PENDING+'</b></div>'
      +'<div style="border:1px solid #dbe6fb;border-radius:8px;padding:8px;background:#fff">Running: <b>'+c.RUNNING+'</b></div>'
      +'<div style="border:1px solid #dbe6fb;border-radius:8px;padding:8px;background:#fff">Terminal: <b>'+(c.SUCCESS+c.FAILED+c.CANCELED+c.TIMEOUT)+'</b></div>';

    if(!jobs.length){$('queueTableWrap').innerHTML='<div class="preset-empty">暂无队列任务</div>'; return;}
    let table='<table style="width:100%;border-collapse:separate;border-spacing:0 8px"><thead><tr><th style="text-align:left;font-size:12px;color:#64748b;padding:6px">Job</th><th style="text-align:left;font-size:12px;color:#64748b;padding:6px">Node</th><th style="text-align:left;font-size:12px;color:#64748b;padding:6px">Action</th><th style="text-align:left;font-size:12px;color:#64748b;padding:6px">Status</th><th style="text-align:left;font-size:12px;color:#64748b;padding:6px">Attempt</th><th style="text-align:left;font-size:12px;color:#64748b;padding:6px">Updated</th></tr></thead><tbody>';
    jobs.forEach(j=>{
      table+='<tr style="background:#fff"><td style="padding:6px;border-top:1px solid #e5ecfa;border-bottom:1px solid #e5ecfa">'+esc(j.job_id||'-')+'</td><td style="padding:6px;border-top:1px solid #e5ecfa;border-bottom:1px solid #e5ecfa">'+esc(j.node_id||'-')+'</td><td style="padding:6px;border-top:1px solid #e5ecfa;border-bottom:1px solid #e5ecfa">'+esc(j.action_type||'-')+'</td><td style="padding:6px;border-top:1px solid #e5ecfa;border-bottom:1px solid #e5ecfa">'+statusBadge(j.status||'')+'</td><td style="padding:6px;border-top:1px solid #e5ecfa;border-bottom:1px solid #e5ecfa">'+esc(j.attempt??0)+'</td><td style="padding:6px;border-top:1px solid #e5ecfa;border-bottom:1px solid #e5ecfa">'+esc(j.updated_at||'-')+'</td></tr>';
    });
    table+='</tbody></table>';
    $('queueTableWrap').innerHTML=table;
  }

  async function boot(){
    state.projectId=(document.querySelector('.ops-page')||{}).dataset?.projectId||'';
    state.jobStatus=(new URLSearchParams(window.location.search).get('job_status')||'').trim().toUpperCase();
    $('btnValidate').onclick=()=>run('validate');
    $('btnExecute').onclick=()=>run('execute');
    if($('btnCreateApproval')) $('btnCreateApproval').onclick=()=>run('approval');
    if($('actTargetType')) $('actTargetType').onchange=function(){ renderTargetOptions(this.value); };
    if($('actTargetKey')) $('actTargetKey').onchange=syncTargetMeta;
    $('btnRefreshPolicy').onclick=loadPolicy;
    $('btnSavePolicy').onclick=savePolicy;
    $('btnRefreshAgents').onclick=loadAgentRegistryAndQueue;
    $('btnRefreshQueue').onclick=loadAgentRegistryAndQueue;
    $('qStatus').onchange=loadAgentRegistryAndQueue;
    if(state.jobStatus && $('qStatus')) $('qStatus').value=state.jobStatus;
    await loadBasics();
    await loadPolicy();
    await loadAgentRegistryAndQueue();
    if(window.location.hash==='#queue'){
      const queueWrap=$('queueTableWrap');
      if(queueWrap && typeof queueWrap.scrollIntoView==='function') queueWrap.scrollIntoView({behavior:'smooth', block:'start'});
    }
  }
  boot();
})();
