(function(){
  const $ = (id)=>document.getElementById(id);

  function safeText(id, value){
    const el = $(id);
    if(el) el.textContent = value;
  }

  function getScope(){
    const shell = document.querySelector('.ops-shell');
    const app = document.querySelector('.ops-shell-app');
    const projectId = (shell && shell.dataset && shell.dataset.projectId) ? String(shell.dataset.projectId) : ((app && app.dataset && app.dataset.projectId) ? String(app.dataset.projectId) : '');
    const envKey = (shell && shell.dataset && shell.dataset.envKey) ? String(shell.dataset.envKey) : ((app && app.dataset && app.dataset.envKey) ? String(app.dataset.envKey) : 'production');
    return { projectId, envKey };
  }

  async function boot(){
    const { projectId, envKey } = getScope();

    const [overview, events] = await Promise.all([
      OpsApi.loadOverview(projectId, envKey),
      OpsApi.loadEvents(20),
    ]);

    const s = (overview && overview.summary) ? overview.summary : {};
    safeText('kpiSla', s.sla_percent == null ? '-' : Number(s.sla_percent).toFixed(1));
    safeText('kpiNodes', s.total_nodes == null ? '-' : String(s.total_nodes));
    safeText('kpiHealthy', s.healthy_nodes == null ? '-' : String(s.healthy_nodes));
    safeText('kpiDegraded', s.degraded_nodes == null ? '-' : String(s.degraded_nodes));
    safeText('kpiOffline', s.offline_nodes == null ? '-' : String(s.offline_nodes));
    safeText('kpiAlerts', s.alert_count == null ? '-' : String(s.alert_count));

    const rows = (events && Array.isArray(events.events)) ? events.events : [];
    if(rows.length){
      const latest = rows[0] || {};
      safeText('eventSummary', '最近事件 ' + rows.length + ' 条，最近动作：' + String(latest.action || '-'));
    }else{
      safeText('eventSummary', '暂无事件');
    }
  }

  boot().then(function(){
    setInterval(function(){ boot().catch(function(){}); }, 30000);
  }).catch((err)=>{
    console.error(err);
    safeText('eventSummary', '加载失败，请刷新重试');
  });
})();

