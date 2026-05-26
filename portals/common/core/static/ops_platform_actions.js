(function(){
  const $=(id)=>document.getElementById(id);
  const esc=(v)=>String(v==null?'':v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const state={projectId:''};
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
    metrics_snapshot:'指标快照',
    log_tail:'日志尾部',
    start:'启动节点',
    stop:'停止节点',
    restart:'重启节点',
    start_all:'全量启动',
    stop_all:'全量停止',
    drain_node:'摘流节点',
    isolate_node:'隔离节点',
    recover_node:'恢复节点',
    kick_session:'踢会话',
    retry_task:'重试任务',
    maintenance:'维护公告',
    feature_toggle:'功能开关',
    whitelist:'白名单',
    mute_chat:'禁言',
    smoke_test:'冒烟测试',
    stress_test:'压力测试',
    db_migration:'数据库迁移'
  };

  function statusBadge(status){
    const s=String(status||'').toUpperCase();
    const cls=(s==='ONLINE'||s==='SUCCESS')?'state-ok':((s==='RUNNING'||s==='PENDING'||s==='DEGRADED')?'state-warn':'state-err');
    return '<span class="state-pill '+cls+'">'+esc(s||'-')+'</span>';
  }

  async function loadBasics(){
    const [nodes,catalog,events]=await Promise.all([OpsApi.loadNodes(),OpsApi.loadActionCatalog(),OpsApi.loadEvents(30)]);
    $('actNode').innerHTML=(nodes.nodes||[]).map(n=>'<option value="'+esc(n.id)+'">'+esc(n.name||n.id)+'</option>').join('');
    const actions=(catalog.actions||catalog.catalog||catalog.data||[]);
    if(!actions.length){
      $('actType').innerHTML='<option value="">暂无可用动作</option>';
    }else{
      const byGroup={};
      actions.forEach(a=>{
        const gid=String(a.groupId||a.group_id||'other');
        if(!byGroup[gid]) byGroup[gid]=[];
        byGroup[gid].push(a);
      });
      const groups=Object.keys(byGroup);
      $('actType').innerHTML=groups.map(gid=>{
        const first=byGroup[gid][0]||{};
        const opts=byGroup[gid].map(a=>{
          const val=String(a.value||a.action||a.action_type||'');
          const label=ACTION_ZH[val] || a.label || val;
          return '<option value="'+esc(val)+'">'+esc(label)+'</option>';
        }).join('');
        return '<optgroup label="'+esc(GROUP_ZH[gid]||first.group||gid)+'">'+opts+'</optgroup>';
      }).join('');
    }
    const list=$('execEvents'); list.innerHTML='';
    (events.events||[]).slice(0,12).forEach(it=>{
      const row=document.createElement('div');
      row.style.cssText='border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:8px';
      row.innerHTML='<div style="display:flex;justify-content:space-between"><b>'+esc(it.action||it.type||'-')+'</b><span style="font-size:11px;color:#64748b">'+esc(it.level||'info')+'</span></div><div style="font-size:11px;color:#64748b">'+esc(it.message||'')+'</div>';
      list.appendChild(row);
    });
  }

  async function run(mode){
    const req={node_id:$('actNode').value,action_type:$('actType').value,target:$('actTarget').value,reason:$('actReason').value,project_id:state.projectId};
    const d=mode==='validate' ? await OpsApi.validateAction(req) : await OpsApi.executeAction(req);
    $('execOutput').textContent=JSON.stringify(d,null,2);
    $('execMeta').textContent=(d.ok?'成功: ':'失败: ')+(d.message||d.error||mode)+(d.trace_id?(' | trace='+d.trace_id):'');
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
    $('btnValidate').onclick=()=>run('validate');
    $('btnExecute').onclick=()=>run('execute');
    $('btnRefreshPolicy').onclick=loadPolicy;
    $('btnSavePolicy').onclick=savePolicy;
    $('btnRefreshAgents').onclick=loadAgentRegistryAndQueue;
    $('btnRefreshQueue').onclick=loadAgentRegistryAndQueue;
    $('qStatus').onchange=loadAgentRegistryAndQueue;
    await loadBasics();
    await loadPolicy();
    await loadAgentRegistryAndQueue();
  }
  boot();
})();
