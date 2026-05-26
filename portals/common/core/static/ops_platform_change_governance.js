(function(){
  const $=(id)=>document.getElementById(id);
  const esc=(v)=>String(v==null?'':v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  function chip(t,cls){return '<span class="chip '+cls+'">'+esc(t)+'</span>';}
  async function load(){
    const d=await OpsApi.changeGovernanceSummary();
    const m=d.metrics||{};
    $('govMetrics').innerHTML=''
      +'<div class="m"><div class="n">待审批</div><div class="v">'+esc(m.pending_approvals??0)+'</div></div>'
      +'<div class="m"><div class="n">高风险动作(24h)</div><div class="v">'+esc(m.high_risk_actions_24h??0)+'</div></div>'
      +'<div class="m"><div class="n">失败动作(24h)</div><div class="v">'+esc(m.failed_actions_24h??0)+'</div></div>'
      +'<div class="m"><div class="n">变更事件(24h)</div><div class="v">'+esc(m.change_events_24h??0)+'</div></div>';

    $('govApprovals').innerHTML=''
      +'<div style="font-size:12px;color:#334155;margin-bottom:8px">审批中心入口：<a href="/admin/approval" style="color:#1d4ed8">/admin/approval</a></div>'
      +'<div style="font-size:12px;color:#64748b">高危动作统一在动作执行中心发起并审批后执行。</div>';

    const frozen=!!(d.window&&d.window.freeze_active);
    $('govWindow').innerHTML=''
      +'<div style="margin-bottom:8px">当前窗口状态：'+(frozen?chip('冻结中','high'):chip('可变更','low'))+'</div>'
      +'<div style="font-size:12px;color:#64748b">建议：生产高峰期使用冻结窗口，灰度批次按 5%-20%-50%-100% 推进。</div>';

    const events=Array.isArray(d.events)?d.events:[];
    if(!events.length){$('govEvents').innerHTML='<div class="preset-empty">暂无治理事件</div>';return;}
    $('govEvents').innerHTML=events.map(it=>'<div style="border:1px solid #e2e8f0;border-radius:8px;background:#f8fafc;padding:8px;margin-bottom:8px">'
      +'<div style="display:flex;justify-content:space-between"><b>'+esc(it.action||it.type||'-')+'</b><span style="font-size:11px;color:#64748b">'+esc(it.time||'-')+'</span></div>'
      +'<div style="font-size:12px;color:#475569">'+esc(it.message||'')+'</div></div>').join('');
  }
  $('btnRefreshGov').onclick=load;
  load();
})();
