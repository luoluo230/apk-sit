(() => {
  const page = document.querySelector("[data-delivery-page]");
  if (!page) return;
  const projectId = page.dataset.projectId;
  const envLabels = {development:"开发环境",testing:"测试环境",staging:"预发环境",production:"生产环境"};
  const statusLabels = {draft:"草稿",building:"构建中",artifacts_ready:"产物已就绪",prechecking:"预检中",precheck_failed:"预检失败",ready:"可发布",awaiting_approval:"待审批",approved:"已审批",publishing:"发布中",published:"已发布",publish_failed:"发布失败",verifying:"验证中",verified:"验证通过",verify_failed:"验证失败",rolled_back:"已回滚",cancelled:"已取消"};
  const artifactStatusLabels = {registered:"已登记",available:"可用",reachable:"可达",missing:"缺失",unreachable:"不可达",invalid:"无效"};
  const artifactTypeLabels = {apk:"APK 安装包",resource:"资源包",config:"配置包",code:"代码热更包"};
  const bindingSourceLabels = {project_default:"项目默认",env_channel:"环境与渠道",version:"大版本覆盖",version_override:"大版本覆盖",default:"项目默认"};
  const esc = (value) => String(value ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
  const api = async (path, options) => {
    const response = await fetch(path, options);
    const result = await response.json();
    if (!response.ok || result.ok === false) throw new Error(result.error || "请求失败");
    return result.data;
  };
  const toast = (message, type="success") => {
    let host = document.querySelector(".toast-stack");
    if (!host) { host = document.createElement("div"); host.className = "toast-stack"; document.body.append(host); }
    const node = document.createElement("div"); node.className = `toast ${type}`; node.textContent = message; host.append(node); setTimeout(() => node.remove(), 3500);
  };
  const status = (value) => `<span class="status-pill ${esc(value)}">${esc(statusLabels[value] || value || "未配置")}</span>`;
  const row = (label, value, extra="") => `<div class="detail-row"><strong>${esc(label)}</strong><span>${esc(value || "-")}</span><b>${extra}</b></div>`;
  const currentContext = () => {
    const source = new URLSearchParams(location.search);
    const query = new URLSearchParams();
    ["env_key","channel_id","platform","version_name","version_code","release_order_id"].forEach(key => source.get(key) && query.set(key, source.get(key)));
    return query.toString() ? `?${query}` : "";
  };

  async function loadOverview() {
    const data = await api(`/api/projects/${encodeURIComponent(projectId)}/overview`);
    const cards = data.environments || [];
    const totalOrders = cards.reduce((sum,item)=>sum+item.release_order_count,0);
    const kpis = [
      ["kpi_health.svg","当前版本",cards.find(x=>x.version_name)?.version_name || "-"],
      ["kpi_health.svg","已生效环境",cards.filter(x=>x.active_bundle_id).length],
      ["kpi_build.svg","今日构建次数",cards.reduce((s,x)=>s+x.processing_count,0)],
      ["kpi_change.svg","待处理变更",cards.reduce((s,x)=>s+x.failed_count+x.pending_approval_count,0)],
      ["kpi_member.svg","发布单总数",totalOrders]
    ];
    document.getElementById("overviewKpis").innerHTML = kpis.map(([icon,label,value])=>`<article class="kpi-card"><img src="/static/project_ui/svg/${icon}" alt=""><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    document.getElementById("environmentCards").innerHTML = cards.map(item=>`<article class="environment-card">
      <div class="environment-head"><h3>${item.env_label}</h3><span class="environment-status ${item.health}">${item.health==="healthy"?"运行中":item.health==="blocked"?"存在阻断":item.health==="warning"?"待处理":item.health==="processing"?"处理中":"未配置"}</span></div>
      <div class="environment-fields"><div><span>渠道</span><strong>${esc(item.channels.join(" / ") || "未配置")}</strong></div><div><span>平台</span><strong>${esc(item.platforms.join(" / ") || "未配置")}</strong></div><div><span>当前版本</span><strong>${esc(item.version_name || "-")} ${esc(item.version_code || "")}</strong></div><div><span>当前拓扑</span><strong>${esc(item.topology_id || "-")}</strong></div></div>
      <div class="health-row"><span>发布单</span><b>${item.release_order_count}</b></div><div class="health-row"><span>待审批</span><b>${item.pending_approval_count}</b></div><div class="health-row"><span>阻断</span><b>${item.failed_count}</b></div>
      <div class="environment-actions"><a class="icon-link" href="/admin/projects/${projectId}/release-orders?env_key=${item.env_key}">查看发布单<img src="/static/project_ui/svg/action_next.svg" alt=""></a><a class="icon-link" href="/admin/projects/${projectId}/topologies?env_key=${item.env_key}">查看拓扑<img src="/static/project_ui/svg/action_next.svg" alt=""></a></div>
    </article>`).join("");
    const events = cards.flatMap(item => item.latest_orders || []).sort((a,b)=>String(b.updated_at).localeCompare(String(a.updated_at))).slice(0,7);
    document.getElementById("overviewActivity").innerHTML = events.length ? events.map(item=>`<a class="activity-row" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}"><span>${status(item.status)}</span><strong>${esc(item.version_name)} / ${esc(item.version_code)} 发布单更新</strong><span>${esc(item.updated_at)}</span></a>`).join("") : '<div class="ui-empty">暂无最近动态</div>';
    document.getElementById("overviewUpdatedAt").textContent = new Date().toLocaleString("zh-CN");
  }

  const renderOrderTable = (items) => {
    const host = document.getElementById("releaseOrderList");
    host.innerHTML = `<div class="order-table-head"><span>发布单 / 版本</span><span>目标</span><span>状态</span><span>拓扑 / Runtime</span><span>更新时间</span><span>操作</span></div>` + (items.length ? items.map(item=>{const context=`?env_key=${encodeURIComponent(item.env_key)}&channel_id=${encodeURIComponent(item.channel_id)}&platform=${encodeURIComponent(item.platform)}&version_name=${encodeURIComponent(item.version_name)}&version_code=${encodeURIComponent(item.version_code)}&release_order_id=${encodeURIComponent(item.release_order_id)}`;return `<div class="order-table-row"><div><strong>${esc(item.release_order_id)}</strong><small>${esc(item.version_name)} / ${esc(item.version_code)}</small></div><div>${esc(envLabels[item.env_key])}<small>${esc(item.channel_name)} / ${esc(item.platform)}</small></div><div>${status(item.status)}</div><div>${esc(item.topology_id || "待解析")}<small>${esc(item.runtime_run_id || "未运行")}</small></div><div>${esc(item.updated_at)}</div><div class="row-actions"><a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}${context}">详情</a>${["draft","artifacts_ready","precheck_failed"].includes(item.status)?`<a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${item.release_order_id}/edit${context}">编辑</a>`:""}</div></div>`;}).join("") : '<div class="ui-empty">当前筛选条件下暂无发布单</div>');
  };
  async function setupOrders() {
    const options = await api(`/api/projects/${projectId}/context-options`);
    const fills = [["env_key",options.environments,"env_key","label"],["channel_id",options.channels,"channel_id","channel_name"],["platform",options.platforms,"value","label"]];
    fills.forEach(([name,items,key,label])=>{const select=page.querySelector(`[data-filter="${name}"]`);items.forEach(item=>select.insertAdjacentHTML("beforeend",`<option value="${esc(item[key])}">${esc(item[label])}</option>`));});
    const statusSelect=page.querySelector('[data-filter="status"]');Object.entries(statusLabels).forEach(([key,label])=>statusSelect.insertAdjacentHTML("beforeend",`<option value="${key}">${label}</option>`));
    const searchParams = new URLSearchParams(location.search);
    page.querySelectorAll("[data-filter]").forEach(select => searchParams.get(select.dataset.filter) && (select.value = searchParams.get(select.dataset.filter)));
    const load = async () => {
      const params=new URLSearchParams();page.querySelectorAll("[data-filter]").forEach(x=>x.value&&params.set(x.dataset.filter,x.value));
      let items=await api(`/api/projects/${projectId}/release-orders?${params}`);
      const search=page.querySelector("[data-order-search]").value.trim().toLowerCase();if(search)items=items.filter(x=>JSON.stringify(x).toLowerCase().includes(search));
      renderOrderTable(items);
      const summary=[["发布单总数",items.length],["处理中",items.filter(x=>["building","prechecking","publishing","verifying"].includes(x.status)).length],["待审批",items.filter(x=>x.status==="awaiting_approval").length],["阻断",items.filter(x=>["precheck_failed","publish_failed","verify_failed"].includes(x.status)).length]];
      document.getElementById("orderSummary").innerHTML=summary.map(([label,value])=>`<article class="kpi-card"><div><span>${label}</span><strong>${value}</strong></div></article>`).join("");
    };
    page.querySelectorAll("[data-filter]").forEach(x=>x.addEventListener("change",load));page.querySelector("[data-order-search]").addEventListener("input",load);page.querySelector("[data-refresh-orders]").addEventListener("click",load);load();
  }

  async function setupOrderForm() {
    const form=document.getElementById("releaseOrderForm"), orderId=page.dataset.orderId;
    const options=await api(`/api/projects/${projectId}/context-options`);
    const fill=(select,items,key,label)=>{select.innerHTML=items.map(item=>`<option value="${esc(item[key])}">${esc(item[label])}</option>`).join("");};
    const valueText=value=>typeof value==="object"&&value!==null?JSON.stringify(value,null,2):String(value??"");
    fill(form.env_key,options.environments,"env_key","label");
    fill(form.channel_id,options.channels,"channel_id","channel_name");
    fill(form.platform,options.platforms,"value","label");

    const selectedVersion=()=>options.versions.find(item=>String(item.id)===String(form.version_id.value))||{};
    const previewCard=(icon,label,value,detail="")=>`<div class="preview-card"><img src="/static/project_ui/svg/${icon}.svg" alt=""><div><span>${esc(label)}</span><strong>${esc(value||"未配置")}</strong>${detail?`<small>${esc(detail)}</small>`:""}</div></div>`;
    const renderPlanPreview=()=>{
      const version=selectedVersion();
      document.getElementById("buildPlanPreview").innerHTML=[
        previewCard("nav_build_artifact","Jenkins 实例",version.jenkins_instance_id||form.jenkins_instance_id.value),
        previewCard("nav_execute","构建任务",version.jenkins_job_id||version.jenkins_job||form.jenkins_job.value),
        previewCard("nav_download_center","资源与配置",version.resource_url||version.resource_path||version.config_url||version.config_path?"已登记":"尚未登记"),
        previewCard("file_android","APK 产物",version.apk_url||version.apk_path?"已登记":"尚未登记")
      ].join("");
      if(!form.jenkins_instance_id.value&&version.jenkins_instance_id)form.jenkins_instance_id.value=version.jenkins_instance_id;
      if(!form.jenkins_job.value&&(version.jenkins_job||version.jenkins_job_id))form.jenkins_job.value=version.jenkins_job||version.jenkins_job_id;
      if(!form.jenkins_params.value&&version.jenkins_params)form.jenkins_params.value=valueText(version.jenkins_params);
      updateCompleteness();
    };
    const renderVersions=()=>{
      const current=form.version_id.value;
      const items=options.versions.filter(x=>x.env_key===form.env_key.value&&x.channel_id===form.channel_id.value&&x.platform===form.platform.value);
      form.version_id.innerHTML=items.length?items.map(x=>`<option value="${esc(x.id)}">${esc(x.version_name)} / ${esc(x.version_code)}</option>`).join(""):'<option value="">当前目标暂无可用 VersionCode</option>';
      if(items.some(x=>String(x.id)===String(current)))form.version_id.value=current;
      renderPlanPreview();
    };
    const updateCompleteness=()=>{
      const required=["env_key","channel_id","platform","version_id","reason","owner","release_window","release_description","validation_plan","rollback_plan"];
      const complete=required.filter(key=>form[key]&&String(form[key].value||"").trim()).length;
      const percent=Math.round(complete/required.length*100);
      document.getElementById("planCompleteness").textContent=`${percent}%`;
      document.getElementById("planCompletenessBar").style.width=`${percent}%`;
      document.getElementById("planCompletenessHint").textContent=percent===100?"计划信息完整，可保存并进入构建。":`还有 ${required.length-complete} 项关键计划信息待补充。`;
    };
    [form.env_key,form.channel_id,form.platform].forEach(x=>x.addEventListener("change",renderVersions));
    form.version_id.addEventListener("change",renderPlanPreview);
    form.addEventListener("input",updateCompleteness);
    page.querySelectorAll("[data-form-step]").forEach(button=>button.addEventListener("click",()=>{
      page.querySelectorAll("[data-form-step]").forEach(item=>item.classList.toggle("active",item===button));
      page.querySelector(`[data-section="${button.dataset.formStep}"]`)?.scrollIntoView({behavior:"smooth",block:"start"});
    }));

    const search=new URLSearchParams(location.search);
    ["env_key","channel_id","platform"].forEach(key=>search.get(key)&&(form[key].value=search.get(key)));
    renderVersions();
    if(orderId){
      const order=await api(`/api/projects/${projectId}/release-orders/${orderId}`);
      ["env_key","channel_id","platform"].forEach(key=>form[key].value=order[key]);
      renderVersions();
      form.version_id.value=order.version_id;
      form.reason.value=order.reason||"";
      Object.entries(order.payload||{}).forEach(([key,value])=>form[key]&&(form[key].value=valueText(value)));
      document.getElementById("resolvedTopology").textContent=order.topology_id||"尚未解析";
      document.getElementById("resolvedRuntime").textContent=order.runtime_run_id||"预检后确认";
      [form.env_key,form.channel_id,form.platform,form.version_id].forEach(x=>x.disabled=true);
      renderPlanPreview();
    }
    updateCompleteness();
    const payload=()=>Object.fromEntries(new FormData(form).entries());
    const save=async(buildAfter=false)=>{
      try{
        if(!form.reportValidity())return;
        page.querySelectorAll("[data-save-order],[data-save-build]").forEach(button=>button.disabled=true);
        let order;
        if(orderId)order=await api(`/api/projects/${projectId}/release-orders/${orderId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        else order=await api(`/api/projects/${projectId}/release-orders`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        document.getElementById("orderSaveStatus").textContent="草稿已保存";
        toast("发布单计划已保存");
        const context=`?env_key=${encodeURIComponent(order.env_key)}&channel_id=${encodeURIComponent(order.channel_id)}&platform=${encodeURIComponent(order.platform)}&version_name=${encodeURIComponent(order.version_name)}&version_code=${encodeURIComponent(order.version_code)}&release_order_id=${encodeURIComponent(order.release_order_id)}`;
        if(buildAfter){
          await api(`/api/projects/${projectId}/release-orders/${order.release_order_id}/build`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
          location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}${context}`;
        }else if(!orderId)location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}/edit${context}`;
      }catch(error){toast(error.message,"error");}
      finally{page.querySelectorAll("[data-save-order],[data-save-build]").forEach(button=>button.disabled=false);}
    };
    page.querySelector("[data-save-order]").addEventListener("click",()=>save(false));
    page.querySelector("[data-save-build]").addEventListener("click",()=>save(true));
  }

  async function loadOrderDetail(){
    const orderId=page.dataset.orderId,item=await api(`/api/projects/${projectId}/release-orders/${orderId}`);
    document.getElementById("orderTitle").innerHTML=`发布单详情 ${status(item.status)}`;document.getElementById("orderSubtitle").textContent=`发布单编号：${item.release_order_id}`;
    const actions=[["edit","编辑计划"],["build","触发构建"],["precheck","执行预检"],["approve","审批通过"],["publish","执行发布"],["verify","执行验证"],["rollback","回滚"],["cancel","取消发布单"]];
    const allowed={edit:["draft","artifacts_ready","precheck_failed"].includes(item.status),build:!["published","verified","rolled_back","cancelled"].includes(item.status),precheck:["draft","artifacts_ready","precheck_failed","ready"].includes(item.status),approve:item.status==="awaiting_approval",publish:["ready","approved"].includes(item.status),verify:["published","verify_failed"].includes(item.status),rollback:Boolean(item.bundle_id&&item.active_bundle_id&&item.bundle_id!==item.active_bundle_id),cancel:!["published","verified","rolled_back","cancelled"].includes(item.status)};
    document.getElementById("orderActions").innerHTML=actions.filter(([key])=>allowed[key]).map(([key,label])=>key==="edit"?`<a class="ui-secondary" href="/admin/projects/${projectId}/release-orders/${orderId}/edit${currentContext()}">${label}</a>`:`<button class="${["publish","verify"].includes(key)?"ui-primary":"ui-secondary"}" data-action="${key}">${label}</button>`).join("");
    document.getElementById("orderMeta").innerHTML=[["目标环境",envLabels[item.env_key]],["版本",`${item.version_name} / ${item.version_code}`],["渠道与平台",`${item.channel_name} / ${item.platform}`],["负责人",item.created_by],["总体状态",statusLabels[item.status]]].map(([label,value])=>`<div class="meta-item"><span>${label}</span><strong>${esc(value)}</strong></div>`).join("");
    const stages=["计划摘要","构建与产物","拓扑与运行态","预检结果","审批","发布执行","验证结果","Bundle 与回滚"];const index={draft:0,building:1,artifacts_ready:1,prechecking:3,precheck_failed:3,ready:3,awaiting_approval:4,approved:4,publishing:5,published:5,verifying:6,verified:7,verify_failed:6,rolled_back:7,cancelled:0}[item.status]??0;document.getElementById("orderSteps").innerHTML=stages.map((label,i)=>`<div class="delivery-step ${i<=index?"active":""} ${i===index&&item.status.includes("failed")?"failed":""}"><b>${i+1}</b>${label}</div>`).join("");
    const check=item.latest_precheck||{},payload=check.payload||{};const artifactProblems=(item.artifacts||[]).filter(x=>["missing","unreachable","invalid"].includes(String(x.status||"").toLowerCase())).map(x=>`${x.artifact_type} ${artifactStatusLabels[x.status]||x.status}`);const problems=[...artifactProblems,...(payload.missing_client_fields||[]),...(payload.missing_profile_fields||[]),...(payload.missing_artifact_fields||[])];payload.runtime_error&&problems.push(payload.runtime_error);document.getElementById("orderAlerts").innerHTML=problems.length?`<div class="alert-card danger"><strong>阻断问题（${problems.length}）</strong><p>${esc(problems.join("；"))}</p></div>`:'<div class="alert-card warning"><strong>下一步建议</strong><p>按发布单当前状态执行下一项交付动作。</p></div>';
    document.getElementById("orderArtifacts").innerHTML=(item.artifacts||[]).map(x=>row(artifactTypeLabels[x.artifact_type]||x.artifact_type,x.artifact_url||x.artifact_path,artifactStatusLabels[x.status]||x.status)).join("")||'<div class="ui-empty">暂无产物</div>';
    document.getElementById("orderRuntime").innerHTML=row("拓扑",item.topology_id,bindingSourceLabels[item.topology_binding_source]||item.topology_binding_source)+row("Runtime",item.runtime_run_id,item.runtime_run_id?"运行中":"未运行");
    document.getElementById("orderPrecheck").innerHTML=check.created_at?row(check.ok?"预检通过":"预检阻断",check.created_at,check.ok?"通过":"失败"):'<div class="ui-empty">尚未执行预检</div>';
    document.getElementById("orderApprovals").innerHTML=(item.approvals||[]).map(x=>row(x.status,x.approved_by||x.requested_by,x.note)).join("")||'<div class="ui-empty">暂无审批记录</div>';
    document.getElementById("orderExecution").innerHTML=row("发布时间",item.published_at,statusLabels[item.status]||item.status)+row("验证状态",statusLabels[item.status],statusLabels[item.status]||item.status);
    document.getElementById("orderBundle").innerHTML=row("Bundle",item.bundle_id,item.bundle_id?"已生成":"未生成")+row("Active Bundle",item.active_bundle_id,item.bundle_id===item.active_bundle_id&&item.bundle_id?"当前生效":"");
    document.getElementById("orderEvents").innerHTML=(item.events||[]).map(x=>`<div class="timeline-row"><strong>${esc(x.event_type)} · ${esc(statusLabels[x.to_status]||x.to_status||"")}</strong><span>${esc(x.actor)} · ${esc(x.created_at)}</span></div>`).join("");
    const dialog=document.getElementById("orderActionDialog"),reason=document.getElementById("orderActionReason");let pendingAction="";
    const closeDialog=()=>{pendingAction="";reason.value="";dialog.classList.add("is-hidden");dialog.setAttribute("aria-hidden","true");};
    const executeAction=async(action,operationReason="")=>{try{await api(`/api/projects/${projectId}/release-orders/${orderId}/${action}`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({reason:operationReason})});toast("操作已提交");loadOrderDetail();}catch(error){toast(error.message,"error");}};
    document.getElementById("orderActionDialogClose").onclick=closeDialog;document.getElementById("orderActionDialogCancel").onclick=closeDialog;
    document.getElementById("orderActionDialogConfirm").onclick=async()=>{const action=pendingAction,operationReason=reason.value.trim();if(["publish","rollback","cancel"].includes(action)&&!operationReason){toast("请填写操作原因","error");return;}closeDialog();await executeAction(action,operationReason);};
    document.querySelectorAll("[data-action]").forEach(button=>button.addEventListener("click",async()=>{const action=button.dataset.action;if(["build","precheck","verify"].includes(action)){await executeAction(action);return;}pendingAction=action;document.getElementById("orderActionDialogTitle").textContent=`确认${button.textContent}`;document.getElementById("orderActionDialogHint").textContent=["publish","rollback","cancel"].includes(action)?"该操作会改变发布状态，请填写原因后确认。":"请确认本次操作影响范围。";dialog.classList.remove("is-hidden");dialog.setAttribute("aria-hidden","false");}));
  }
  const type=page.dataset.deliveryPage;
  if(type==="overview"){loadOverview().catch(error=>toast(error.message,"error"));page.querySelector("[data-refresh-overview]")?.addEventListener("click",loadOverview);}
  if(type==="orders")setupOrders().catch(error=>toast(error.message,"error"));
  if(type==="order-form")setupOrderForm().catch(error=>toast(error.message,"error"));
  if(type==="order-detail")loadOrderDetail().catch(error=>toast(error.message,"error"));
})();
