(function(){
  const $=(id)=>document.getElementById(id);
  const esc=(v)=>String(v==null?'':v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const state={projectId:'',envKey:'production',rows:[],filtered:[]};
  const statusCls=(s)=>s==='ONLINE'||s==='PASS'?'ok':(s==='DEGRADED'?'warn':'err');

  function actionHref(act){
    if(act.href) return act.href;
    const q=new URLSearchParams();
    q.set('project_id', state.projectId||'');
    q.set('env_key', state.envKey||'production');
    if(act.target_key) q.set('target_key', act.target_key);
    if(act.action_type) q.set('action_type', act.action_type);
    return '/admin/projects/'+encodeURIComponent(state.projectId)+'/actions?'+q.toString();
  }

  function renderMetrics(summary){
    const s=summary||{};
    $('diagMetrics').innerHTML=''
      +'<div class="m"><div class="n">总节点</div><div class="v">'+esc(s.total_nodes??state.rows.length)+'</div></div>'
      +'<div class="m"><div class="n">健康</div><div class="v">'+esc(s.ok_nodes??0)+'</div></div>'
      +'<div class="m"><div class="n">告警</div><div class="v">'+esc(s.warning??0)+'</div></div>'
      +'<div class="m"><div class="n">严重</div><div class="v">'+esc(s.critical??0)+'</div></div>';
  }

  function applyFilters(){
    const q=String($('fNode').value||'').trim().toLowerCase(),role=String($('fRole').value||''),status=String($('fStatus').value||'');
    state.filtered=state.rows.filter(r=>{
      const id=String(r.id||r.node_id||r.name||'').toLowerCase();
      if(q && !id.includes(q) && !String(r.agent_id||'').toLowerCase().includes(q)) return false;
      if(role && String(r.role||'')!==role) return false;
      const s=String(r.status||'UNKNOWN').toUpperCase();
      if(status && s!==status) return false;
      return true;
    });
    renderTable();
  }

  function renderTable(){
    if(!state.filtered.length){$('diagTableWrap').innerHTML='<div style="border:1px dashed #cbd5e1;background:#f8fafc;border-radius:10px;padding:14px;color:#64748b">暂无匹配数据</div>';return;}
    let html='<table><thead><tr><th>节点</th><th>角色</th><th>Agent</th><th>Probe</th><th>状态</th><th>检查</th><th>修复</th></tr></thead><tbody>';
    state.filtered.forEach(r=>{
      const s=String(r.status||'UNKNOWN').toUpperCase();
      const probe=String(r.probe_status||'-').toUpperCase();
      const fixes=(r.fix_actions||[]).map(act=>'<a class="btn" style="padding:2px 8px;font-size:11px;margin-right:4px" href="'+esc(actionHref(act))+'">'+esc(act.label||act.action_type||'修复')+'</a>').join('');
      html+='<tr>'
        +'<td>'+esc(r.id||r.node_id||r.name||'-')+'</td>'
        +'<td>'+esc(r.role||'-')+'</td>'
        +'<td>'+esc(r.agent_id||'-')+'</td>'
        +'<td><span class="badge '+statusCls(probe)+'">'+esc(probe)+'</span></td>'
        +'<td><span class="badge '+statusCls(s)+'">'+esc(s)+'</span></td>'
        +'<td>'+esc(r.message||r.onboarding_check||'')+'</td>'
        +'<td>'+(fixes||'-')+'</td>'
        +'</tr>';
    });
    html+='</tbody></table>';
    $('diagTableWrap').innerHTML=html;
  }

  function exportCsv(){
    const lines=['id,role,agent_id,probe_status,status,message'];
    state.filtered.forEach(r=>{
      const msg=String(r.message||r.onboarding_check||'').replace(/"/g,'""');
      lines.push([r.id||r.node_id||'',r.role||'',r.agent_id||'',r.probe_status||'',String(r.status||'UNKNOWN').toUpperCase(),'"'+msg+'"'].join(','));
    });
    const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'});
    const url=URL.createObjectURL(blob);
    const a=document.createElement('a');
    a.href=url;a.download='ops_diagnostics_'+Date.now()+'.csv';a.click();URL.revokeObjectURL(url);
  }

  async function loadData(){
    const d=await OpsApi.loadDiagnosticsSummary(state.projectId, state.envKey);
    state.rows=(d.checks||[]).map(x=>Object.assign({},x,{id:x.node_id||x.id||x.name}));
    const roleSet=new Set(state.rows.map(r=>String(r.role||'')).filter(Boolean));
    $('fRole').innerHTML='<option value="">全部角色</option>'+Array.from(roleSet).map(r=>'<option value="'+esc(r)+'">'+esc(r)+'</option>').join('');
    renderMetrics(d.summary||{});
    state.filtered=[...state.rows];
    renderTable();
  }

  async function boot(){
    const page=document.querySelector('.diag-page')||{};
    state.projectId=page.dataset?.projectId||'';
    state.envKey=page.dataset?.envKey||document.querySelector('.ops-shell-app')?.dataset?.envKey||'production';
    $('btnRefreshDiag').onclick=loadData;
    $('btnApplyFilter').onclick=applyFilters;
    $('btnExportDiag').onclick=exportCsv;
    await loadData();
  }
  boot();
})();
