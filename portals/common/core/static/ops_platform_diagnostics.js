(function(){
  const $=(id)=>document.getElementById(id);
  const esc=(v)=>String(v==null?'':v).replace(/[&<>"']/g,s=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[s]));
  const state={projectId:'',rows:[],filtered:[]};
  const statusCls=(s)=>s==='ONLINE'?'ok':(s==='DEGRADED'?'warn':'err');
  function renderMetrics(){
    let online=0,degraded=0,offline=0;
    state.rows.forEach(r=>{const s=String(r.status||'UNKNOWN').toUpperCase();if(s==='ONLINE')online++;else if(s==='DEGRADED')degraded++;else offline++;});
    $('diagMetrics').innerHTML='<div class="m"><div class="n">总节点</div><div class="v">'+state.rows.length+'</div></div><div class="m"><div class="n">健康</div><div class="v">'+online+'</div></div><div class="m"><div class="n">退化</div><div class="v">'+degraded+'</div></div><div class="m"><div class="n">高风险</div><div class="v">'+offline+'</div></div>';
  }
  function applyFilters(){
    const q=String($('fNode').value||'').trim().toLowerCase(),role=String($('fRole').value||''),status=String($('fStatus').value||'');
    state.filtered=state.rows.filter(r=>{const id=String(r.id||r.name||'').toLowerCase();if(q&&!id.includes(q))return false;if(role&&String(r.role||'')!==role)return false;const s=String(r.status||'UNKNOWN').toUpperCase();if(status&&s!==status)return false;return true;});
    renderTable();
  }
  function renderTable(){
    if(!state.filtered.length){$('diagTableWrap').innerHTML='<div style="border:1px dashed #cbd5e1;background:#f8fafc;border-radius:10px;padding:14px;color:#64748b">暂无匹配数据</div>';return;}
    let html='<table><thead><tr><th>节点</th><th>角色</th><th>状态</th><th>检查</th></tr></thead><tbody>';
    state.filtered.forEach(r=>{const s=String(r.status||'UNKNOWN').toUpperCase();html+='<tr><td>'+esc(r.id||r.name||'-')+'</td><td>'+esc(r.role||'-')+'</td><td><span class="badge '+statusCls(s)+'">'+esc(s)+'</span></td><td>'+esc(r.message||r.onboarding_check||'')+'</td></tr>';});
    html+='</tbody></table>';
    $('diagTableWrap').innerHTML=html;
  }
  function exportCsv(){
    const lines=['id,role,status,message'];state.filtered.forEach(r=>{const msg=String(r.message||r.onboarding_check||'').replace(/"/g,'""');lines.push([r.id||'',r.role||'',String(r.status||'UNKNOWN').toUpperCase(),'"'+msg+'"'].join(','));});
    const blob=new Blob([lines.join('\n')],{type:'text/csv;charset=utf-8;'});const url=URL.createObjectURL(blob);const a=document.createElement('a');a.href=url;a.download='ops_diagnostics_'+Date.now()+'.csv';a.click();URL.revokeObjectURL(url);
  }
  async function loadData(){
    const [nodes,onb]=await Promise.all([OpsApi.loadNodes(),OpsApi.loadOnboarding()]);
    const roleMap={};(nodes.nodes||[]).forEach(n=>roleMap[n.id]=n.role||'');
    state.rows=(onb.nodes||onb.items||[]).map(x=>Object.assign({},x,{role:x.role||roleMap[x.id]||''}));
    const roleSet=new Set(state.rows.map(r=>String(r.role||'')).filter(Boolean));
    $('fRole').innerHTML='<option value="">全部角色</option>'+Array.from(roleSet).map(r=>'<option value="'+esc(r)+'">'+esc(r)+'</option>').join('');
    renderMetrics();state.filtered=[...state.rows];renderTable();
  }
  async function boot(){
    state.projectId=(document.querySelector('.diag-page')||{}).dataset?.projectId||'';
    $('btnRefreshDiag').onclick=loadData;$('btnApplyFilter').onclick=applyFilters;$('btnExportDiag').onclick=exportCsv;
    await loadData();
  }
  boot();
})();
