(function(){
  const $=(id)=>document.getElementById(id);
  const esc=(v)=>String(v==null?'':v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const state={projectId:'', window:{}, scope:{}};

  function chip(t,cls){return '<span class="chip '+cls+'">'+esc(t)+'</span>';}

  async function loadScope(){
    const topologies=await OpsApi.loadTopologies({project_id:state.projectId});
    const rows=(topologies&&topologies.topologies)||[];
    const hit=rows.find(t=>t.is_default)||rows[0]||{};
    state.scope={
      project_id:state.projectId,
      env_key:hit.env_key||'production',
      topology_id:hit.topology_id||''
    };
    if($('govTopologyId')) $('govTopologyId').value=state.scope.topology_id||'';
    if($('govEnvKey')) $('govEnvKey').value=state.scope.env_key||'production';
  }

  async function load(){
    await loadScope();
    const d=await OpsApi.changeGovernanceSummary(state.projectId);
    const m=d.metrics||{};
    state.window=d.window||{};
    $('govMetrics').innerHTML=''
      +'<div class="m"><div class="n">待审批</div><div class="v">'+esc(m.pending_approvals??0)+'</div></div>'
      +'<div class="m"><div class="n">高风险动作(24h)</div><div class="v">'+esc(m.high_risk_actions_24h??0)+'</div></div>'
      +'<div class="m"><div class="n">失败动作(24h)</div><div class="v">'+esc(m.failed_actions_24h??0)+'</div></div>'
      +'<div class="m"><div class="n">变更事件(24h)</div><div class="v">'+esc(m.change_events_24h??0)+'</div></div>';

    $('govApprovals').innerHTML=''
      +'<div style="font-size:12px;color:#334155;margin-bottom:8px">审批中心：<a href="/admin/approval" style="color:#1d4ed8">/admin/approval</a></div>'
      +'<div style="font-size:12px;color:#64748b;margin-bottom:8px">高危动作在动作执行中心发起 → 创建审批 → 审批通过后执行。</div>'
      +'<a class="btn" href="/admin/projects/'+encodeURIComponent(state.projectId)+'/actions">打开动作执行中心</a>';

    const frozen=!!(state.window&&state.window.freeze_active);
    const runtimeActive=!!(state.window&&state.window.runtime_active);
    const runtimeLive=!!(state.window&&state.window.runtime_live_verified);
    const runtimeLiveCount=Number((state.window&&state.window.runtime_live_count)||0);
    const runtimeLiveTotal=Number((state.window&&state.window.runtime_live_total)||0);
    const runtimeChip=runtimeLive
      ? chip('服务运行中 '+runtimeLiveCount+'/'+runtimeLiveTotal,'low')
      : (runtimeActive?chip('编排记录活跃（探活未通过） '+String(state.window.runtime_run_id||''),'mid'):chip('未运行','low'));
    $('govWindow').innerHTML=''
      +'<div style="margin-bottom:8px">变更冻结：'+(frozen?chip('冻结中','high'):chip('可变更','low'))+'</div>'
      +'<div style="margin-bottom:8px">拓扑运行：'+runtimeChip+'</div>'
      +'<div style="font-size:12px;color:#64748b;margin-bottom:8px">'+esc(state.window.freeze_reason||'可通过下方按钮开启/解除冻结窗口。')+'</div>'
      +'<div class="row" style="gap:8px;flex-wrap:wrap">'
      +'<button id="btnFreezeOn" class="btn">开启冻结</button>'
      +'<button id="btnFreezeOff" class="btn">解除冻结</button>'
      +'<button id="btnFlowStart" class="btn success">拓扑启动</button>'
      +'<button id="btnFlowStop" class="btn">拓扑停止</button>'
      +'<a class="btn" href="/admin/projects/'+encodeURIComponent(state.projectId)+'/topologies?env_key='+encodeURIComponent(state.scope.env_key||'production')+'&topology_id='+encodeURIComponent(state.scope.topology_id||'')+'">进入拓扑编排</a>'
      +'</div>'
      +'<div id="govFlowMeta" class="ops-note" style="margin-top:8px"></div>';

    $('btnFreezeOn').onclick=()=>setFreeze(true);
    $('btnFreezeOff').onclick=()=>setFreeze(false);
    $('btnFlowStart').onclick=()=>runFlow('start');
    $('btnFlowStop').onclick=()=>runFlow('stop');

    const events=Array.isArray(d.events)?d.events:[];
    if(!events.length){$('govEvents').innerHTML='<div class="preset-empty">暂无治理事件</div>';return;}
    $('govEvents').innerHTML=events.map(it=>'<div style="border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:8px;margin-bottom:8px">'
      +'<div style="display:flex;justify-content:space-between"><b>'+esc(it.action||it.type||'-')+'</b><span style="font-size:11px;color:#64748b">'+esc(it.time||'-')+'</span></div>'
      +'<div style="font-size:12px;color:#475569">'+esc(it.message||'')+'</div></div>').join('');
  }

  async function setFreeze(active){
    const reason=prompt(active?'请输入冻结原因':'解除冻结说明（可选）', active?'生产高峰期变更冻结':'解除冻结')||'';
    const d=await OpsApi.setChangeFreeze({project_id:state.projectId, active:active, reason:reason});
    $('govFlowMeta').textContent=(d.ok?'冻结状态已更新':'操作失败')+(d.message?(' | '+d.message):'');
    await load();
  }

  async function runFlow(op){
    const payload=Object.assign({}, state.scope, {op:op});
    const d=await OpsApi.runtimeFlowControl(payload);
    $('govFlowMeta').textContent=(d.ok?'流程已提交: '+op:'流程失败')+(d.run_id?(' | run='+d.run_id):'')+(d.message?(' | '+d.message):'');
    await load();
  }

  async function boot(){
    state.projectId=(document.querySelector('.ops-page')||{}).dataset?.projectId||'';
    $('btnRefreshGov').onclick=load;
    await load();
  }
  boot();
})();
