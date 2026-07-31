/* Release order create/edit form — extracted from project_delivery.js */
(function (global) {
  "use strict";
  async function setupOrderForm(ctx) {
    const { page, projectId, api, toast } = ctx;
    const form=document.getElementById("releaseOrderForm"), orderId=page.dataset.orderId;
    const search=new URLSearchParams(location.search);
    const envFromUrl=search.get("env_key")||"";
    const draftKey=`release-order-draft:${projectId}:${orderId||"new"}`;
    const formatTime=()=>{const d=new Date();return `${String(d.getHours()).padStart(2,"0")}:${String(d.getMinutes()).padStart(2,"0")}:${String(d.getSeconds()).padStart(2,"0")}`;};
    const touchAutosave=(saved=false)=>{
      const el=document.getElementById("orderAutosave");
      if(!el)return;
      el.textContent=saved?`已自动保存于 ${formatTime()}`:"编辑中…";
      el.classList.toggle("saved",saved);
    };
    const bindTagField=(input)=>{
      if(!input||input.dataset.tagBound)return;
      input.dataset.tagBound="1";
      const wrap=document.createElement("div");
      wrap.className="ro-tag-wrap";
      input.parentElement.appendChild(wrap);
      const render=()=>{
        const tags=String(input.value||"").split(/[,，;；\n]/).map(x=>x.trim()).filter(Boolean);
        wrap.innerHTML=tags.map((tag,i)=>`<span class="ro-tag">${esc(tag)}<button type="button" data-tag-remove="${i}" aria-label="移除">×</button></span>`).join("");
        wrap.querySelectorAll("[data-tag-remove]").forEach(btn=>btn.addEventListener("click",()=>{
          const idx=Number(btn.dataset.tagRemove);
          const next=tags.filter((_,j)=>j!==idx);
          input.value=next.join(", ");
          render();
          input.dispatchEvent(new Event("input",{bubbles:true}));
        }));
      };
      input.addEventListener("input",render);
      input.addEventListener("blur",render);
      render();
    };
    page.querySelectorAll("[data-tag-field]").forEach(bindTagField);
    const descArea=form.release_description;
    const descCount=document.getElementById("orderDescCount");
    const syncDescCount=()=>{if(descCount&&descArea)descCount.textContent=`${(descArea.value||"").length} / 500`;};
    if(descArea){descArea.addEventListener("input",syncDescCount);syncDescCount();}
    const syncGrayFieldVisibility=()=>{
      const isGray=(form.release_strategy?.value||"standard")==="gray";
      ["gray_strategy","gray_ratio","gray_duration","gray_success_action"].forEach((name)=>{
        const field=form[name];
        if(!field)return;
        const label=field.closest("label");
        if(label)label.classList.toggle("is-hidden",!isGray);
        field.disabled=!isGray;
      });
      const grayPanel=document.getElementById("orderGrayPlanPanel");
      const grayList=document.getElementById("orderGrayPlanList");
      const journeyLink=document.getElementById("orderGrayJourneyLink");
      if(grayPanel)grayPanel.classList.toggle("is-hidden",!isGray);
      if(grayList&&isGray){
        const ratio=form.gray_ratio?.value||"10";
        const strategy=form.gray_strategy?.selectedOptions?.[0]?.textContent||form.gray_strategy?.value||"ratio";
        const duration=form.gray_duration?.value||"—";
        const action=form.gray_success_action?.selectedOptions?.[0]?.textContent||form.gray_success_action?.value||"manual";
        grayList.innerHTML=[
          `灰度比例：${esc(ratio)}%`,
          `灰度策略：${esc(strategy)}`,
          `观察时长：${esc(duration)} 分钟`,
          `成功后：${esc(action)}`,
        ].map((x)=>`<li>${x}</li>`).join("");
      }
      if(journeyLink){
        const env=form.env_key?.value||"";
        const channel=form.channel_id?.value||"";
        const platform=form.platform?.value||"";
        if(env&&channel&&platform){
          const qs=new URLSearchParams({env_key:env,channel_id:channel,platform});
          journeyLink.href=`/admin/projects/${projectId}/versions?${qs}`;
          journeyLink.classList.remove("is-hidden");
        }else{
          journeyLink.classList.add("is-hidden");
        }
      }
    };
    const updateRiskPanel=()=>{
      const levelEl=document.getElementById("orderRiskLevel");
      const listEl=document.getElementById("orderRiskList");
      if(!levelEl||!listEl)return;
      const env=form.env_key.value;
      const channel=form.channel_id.selectedOptions[0]?.textContent||form.channel_id.value;
      const platform=form.platform.selectedOptions[0]?.textContent||form.platform.value;
      const strategy=form.release_strategy?.value||"standard";
      const audience=form.target_audience?.selectedOptions[0]?.textContent||"全部用户";
      const isProd=env==="production";
      levelEl.textContent=isProd?"高风险":env==="staging"?"中风险":"低风险";
      levelEl.className=`ro-risk-tag ${isProd?"high":env==="staging"?"medium":"low"}`;
      const items=[
        `目标环境：${form.env_key.selectedOptions[0]?.textContent||env}${isProd?"（生产）":""}`,
        `影响范围：${audience}`,
        `渠道 / 平台：${channel} / ${platform}`,
        strategy==="gray"?"发布方式：灰度发布（推荐）":"发布方式：全量发布",
      ];
      const version=selectedVersion();
      if(version?.version_name)items.push(`VersionCode：${version.version_name} / ${version.version_code||""}`);
      listEl.innerHTML=items.map(x=>`<li>${esc(x)}</li>`).join("");
      form.env_key.dataset.risk=isProd?"production":"";
    };
    const updateRuntimeStats=()=>{
      const badge=document.getElementById("orderRuntimeBadge");
      const countEl=document.getElementById("orderInstanceCount");
      const topoVer=document.getElementById("orderTopologyVersion");
      const delivery=formContext.delivery_readiness||{};
      const checks=delivery.checks||{};
      if(badge){
        const ready=Boolean(checks.topology);
        badge.textContent=ready?"运行中":"待解析";
        badge.className=`ro-runtime-badge ${ready?"running":"unknown"}`;
      }
      if(countEl){
        const inst=delivery.runtime_instances;
        countEl.textContent=typeof inst==="object"&&inst?`${inst.ready||0} / ${inst.total||0} 台`:checks.topology?"— / — 台":"—";
      }
      if(topoVer&&!topoVer.value)topoVer.placeholder=checks.topology?"保存后解析":"保存后按绑定规则解析";
    };
    const updateJenkinsDisplay=(version, buildLinks={})=>{
      const instSel=document.getElementById("orderJenkinsDisplay");
      const jobSel=document.getElementById("orderJobDisplay");
      const paramsInput=document.getElementById("orderJenkinsParamsDisplay");
      const inst=version?.jenkins_instance_id||form.jenkins_instance_id?.value||"";
      const job=version?.jenkins_job_id||version?.jenkins_job||form.jenkins_job?.value||"";
      const ensureFieldLink=(selectEl,href,label)=>{
        if(!selectEl?.parentElement)return;
        let hint=selectEl.parentElement.querySelector(".ro-field-config-link");
        if(!href){hint?.remove();return;}
        if(!hint){
          hint=document.createElement("a");
          hint.className="ro-field-config-link ro-config-link";
          selectEl.parentElement.appendChild(hint);
        }
        hint.href=href;
        hint.textContent=label;
      };
      if(instSel){
        instSel.innerHTML=inst?`<option>${esc(inst)}</option>`:'<option>未配置</option>';
        ensureFieldLink(instSel,inst?"":(buildLinks.jenkinsInstance||buildLinks.jenkinsJob||""),"去配置 Jenkins 实例 →");
      }
      if(jobSel){
        jobSel.innerHTML=job?`<option>${esc(job)}</option>`:'<option>未配置</option>';
        ensureFieldLink(jobSel,job?"":(buildLinks.jenkinsJob||""),"去配置 Job / 任务 →");
      }
      if(paramsInput){
        const envKey=form.env_key.value||"prod";
        const channel=form.channel_id.value||"release";
        const platform=form.platform.value||"all";
        const existing=String(paramsInput.value||"").trim();
        if(!existing){
          paramsInput.value=`ENV=${envKey}, CHANNEL=${channel}, PLATFORM=${platform}`;
        }
        bindTagField(paramsInput);
      }
    };
    const applyOrderTemplate=(kind)=>{
      const templates={
        routine:{release_reason_type:"feature",release_strategy:"standard",gray_ratio:"",validation_items:"订单创建流程, 支付结果页跳转",validation_task:"RC-UI-官网验证"},
        hotfix:{release_reason_type:"hotfix",release_strategy:"standard",gray_ratio:"5",gray_duration:"15",validation_items:"核心链路回归",validation_task:""},
        gray:{release_reason_type:"feature",release_strategy:"gray",gray_strategy:"ratio",gray_ratio:"10",gray_duration:"30",gray_success_action:"automatic",validation_items:"订单创建流程, 支付结果页跳转, 消息推送验证"},
      };
      const preset=templates[kind]||{};
      Object.entries(preset).forEach(([key,val])=>{if(form[key])form[key].value=val;});
      page.querySelectorAll("[data-tag-field]").forEach((input)=>{if(input.dataset.tagBound){input.dispatchEvent(new Event("input",{bubbles:true}));}});
      syncDescCount();
      syncGrayFieldVisibility();
      updateRiskPanel();
      updateCompleteness();
      touchAutosave(false);
      toast(kind==="hotfix"?"已应用紧急修复模板":kind==="gray"?"已应用灰度发布模板":"已应用常规发布模板");
    };
    page.querySelectorAll("[data-order-template]").forEach(btn=>btn.addEventListener("click",()=>applyOrderTemplate(btn.dataset.orderTemplate)));
    document.getElementById("btnCopyPlan")?.addEventListener("click",async()=>{
      try{
        await navigator.clipboard.writeText(JSON.stringify(payload(),null,2));
        toast("发布计划已复制到剪贴板");
      }catch(_e){toast("复制失败，请手动复制表单内容","error");}
    });
    let autosaveTimer=null;
    const scheduleDraft=()=>{
      touchAutosave(false);
      clearTimeout(autosaveTimer);
      autosaveTimer=setTimeout(()=>{
        try{localStorage.setItem(draftKey,JSON.stringify(payload()));touchAutosave(true);}catch(_e){/* ignore quota */}
      },1200);
    };
    form.addEventListener("input",scheduleDraft);
    form.addEventListener("change",scheduleDraft);
    touchAutosave(false);
    const options=await api(`/api/projects/${projectId}/context-options${envFromUrl?`?env_key=${encodeURIComponent(envFromUrl)}`:""}`);
    try {
      const listResponse=await fetch(`/admin/projects/${projectId}/versions/list`,{credentials:"same-origin"});
      const listPayload=await listResponse.json();
      if(listResponse.ok&&Array.isArray(listPayload.versions)){
        const enriched=new Map(listPayload.versions.map((item)=>[String(item.id),item]));
        options.versions=(options.versions||[]).map((item)=>({...item,...(enriched.get(String(item.id))||{})}));
      }
    }catch(_error){/* keep context-options versions */}
    const fill=(select,items,key,label)=>{select.innerHTML=items.map(item=>`<option value="${esc(item[key])}">${esc(item[label])}</option>`).join("");};
    const valueText=value=>typeof value==="object"&&value!==null?JSON.stringify(value,null,2):String(value??"");
    fill(form.env_key,options.environments,"env_key","label");
    fill(form.channel_id,options.channels,"channel_id","channel_name");
    fill(form.platform,options.platforms,"value","label");
    const topologySelect = form.target_topology_id;
    if (topologySelect) {
      try {
        const topoResponse = await fetch(`/api/projects/${encodeURIComponent(projectId)}/topologies`, { credentials: "same-origin" });
        const topoData = await topoResponse.json();
        const topologies = topoData.data?.topologies || [];
        topologySelect.innerHTML = '<option value="">按绑定规则自动解析</option>' + topologies.map((item) => `<option value="${esc(item.topology_id)}">${esc(item.name || item.topology_id)}</option>`).join("");
      } catch (_error) {
        topologySelect.innerHTML = '<option value="">按绑定规则自动解析</option>';
      }
    }

    const selectedVersion=()=>options.versions.find(item=>String(item.id)===String(form.version_id.value))||{};
    const effectivePipelineCache=new Map();
    let formContext={required_fields:["reason","owner"],release_policy:{form_depth:"minimal"},delivery_readiness:{ready:false,pipeline_ready:false,percent:0},build_config_href:""};
    const loadFormContext=async(version)=>{
      const params=new URLSearchParams();
      if(version?.id)params.set("version_id",version.id);
      if(form.env_key.value)params.set("env_key",form.env_key.value);
      if(form.channel_id.value)params.set("channel_id",form.channel_id.value);
      if(form.platform.value)params.set("platform",form.platform.value);
      try{
        const data=await api(`/api/projects/${projectId}/release-order-form-context?${params}`);
        formContext=data||formContext;
        applyReleaseDefaults(formContext.release_defaults||{});
        applyFormDepth(formContext.form_depth||formContext.release_policy?.form_depth||"standard");
        syncDescCount();
      }catch(_error){/* keep defaults */}
      updateCompleteness();
      updatePipelineGate();
      refreshPipelineSourcePill();
    };
    const applyReleaseDefaults=(defaults)=>{
      if(!defaults||typeof defaults!=="object")return;
      Object.entries(defaults).forEach(([key,value])=>{
        if(!form[key])return;
        if(!String(form[key].value||"").trim()&&String(value||"").trim())form[key].value=String(value);
      });
    };
    const sectionJumpMap={target:"target",build:"build",runtime:"runtime",strategy:"strategy",verify:"verify",rollback:"rollback"};
    const unfoldSection=(key)=>{
      const section=form.querySelector(`[data-section="${sectionJumpMap[key]||key}"]`);
      if(!section)return null;
      section.classList.remove("is-folded");
      section.scrollIntoView({behavior:"smooth",block:"start"});
      return section;
    };
    const bindSectionNavigation=()=>{
      form.querySelectorAll(".ro-section .ro-section-head").forEach((head)=>{
        const section=head.closest(".ro-section");
        if(!section)return;
        const titleRow=head.querySelector(":scope > div")||head;
        let toggle=titleRow.querySelector(".ro-section-toggle");
        if(section.dataset.section!=="target"){
          if(!toggle){
            toggle=document.createElement("span");
            toggle.className="ro-section-toggle";
            titleRow.appendChild(toggle);
          }
          toggle.textContent=section.classList.contains("is-folded")?"展开查看":"收起";
          if(!head.dataset.sectionNavBound){
            head.dataset.sectionNavBound="1";
            head.addEventListener("click",()=>{
              section.classList.toggle("is-folded");
              toggle.textContent=section.classList.contains("is-folded")?"展开查看":"收起";
            });
          }
        }else if(toggle)toggle.remove();
      });
      const guideItems=page.querySelectorAll(".ro-guide-list li");
      const guideKeys=["target","build","runtime","strategy","verify","rollback"];
      guideItems.forEach((item,index)=>{
        item.classList.add("is-link");
        item.addEventListener("click",()=>unfoldSection(guideKeys[index]||"target"));
      });
      document.getElementById("orderFormJourneyProgress")?.querySelectorAll("[data-jump]").forEach((node)=>{
        node.addEventListener("click",()=>{
          const jump=node.dataset.jump||"target";
          if(jump==="plan")unfoldSection("build");
          else if(jump==="execute")unfoldSection("strategy");
          else unfoldSection("target");
        });
      });
    };
    const applyFormDepth=(depth)=>{
      const root=page.querySelector(".order-form-app")||page;
      const minimal=depth==="minimal";
      const standard=depth==="standard";
      root.classList.toggle("order-form-minimal",minimal);
      root.classList.toggle("order-form-standard",standard&&!minimal);
      form.querySelectorAll(".ro-section").forEach((section)=>{
        section.classList.remove("is-collapsed-section");
        const key=section.dataset.section||"";
        if(key==="target"){section.classList.remove("is-folded");return;}
        if(minimal|| (standard&&key==="rollback"))section.classList.add("is-folded");
        else section.classList.remove("is-folded");
        const toggle=section.querySelector(".ro-section-toggle");
        if(toggle)toggle.textContent=section.classList.contains("is-folded")?"展开查看":"收起";
      });
      page.querySelectorAll(".order-field-optional").forEach((el)=>{
        el.classList.toggle("is-hidden-field",minimal);
      });
      const miniSummary=document.getElementById("orderMinimalBuildSummary");
      if(miniSummary)miniSummary.hidden=!minimal;
      bindSectionNavigation();
    };
    const updatePipelineGate=()=>{
      const delivery=formContext.delivery_readiness||{};
      const pipelineReady=Boolean(delivery.pipeline_ready);
      const btnNext=document.getElementById("btnFormNext");
      const btnConfig=document.getElementById("btnConfigurePipeline");
      const artifactsReady=Boolean(delivery.checks?.artifacts);
      if(btnNext){
        btnNext.disabled=!pipelineReady;
        btnNext.textContent=pipelineReady?(artifactsReady?"下一步：保存并预检":"下一步：保存并触发构建"):"下一步：先配置管线";
        btnNext.title=pipelineReady?"":(delivery.blocker_hint||"请先在版本组配置 Jenkins 实例、Job 与四步管线。");
      }
      if(btnConfig){
        const href=formContext.build_config_href||"";
        if(!pipelineReady&&href){
          btnConfig.href=href;
          btnConfig.classList.remove("is-hidden");
        }else btnConfig.classList.add("is-hidden");
      }
      const gateHint=document.getElementById("orderPipelineGateHint");
      if(gateHint){
        const pipeline=delivery.pipeline||{};
        const hint=String(pipeline.blocker_hint||"").trim();
        if(!pipelineReady&&hint){
          gateHint.textContent=`${hint.startsWith("待")?hint:`待完善：${hint}`}。`;
          gateHint.hidden=false;
        }else{
          gateHint.textContent="";
          gateHint.hidden=true;
        }
      }
    };
    const versionContextQuery=(version)=>{
      if(!version||(!version.id&&!version.version_name))return "";
      return buildScopeQuery({
        env_key:version.env_key,
        channel_id:version.channel_id,
        platform:version.platform,
        version_id:version.id,
        version_name:version.version_name,
        version_code:version.version_code,
      }).replace(/^\?/,"");
    };
    const updateFormJourney=()=>{
      const delivery=formContext.delivery_readiness||{};
      const pipelineReady=Boolean(delivery.pipeline_ready);
      const planPercent=Number(document.getElementById("planCompleteness")?.textContent?.replace("%","")||0);
      const phaseIndex=pipelineReady?(planPercent>=100?2:1):0;
      renderJourneyProgress(document.getElementById("orderFormJourneyProgress"), ["准备","构建","发版"], phaseIndex);
    };
    const previewCard=(icon,label,value,detail="",href="",linkLabel="去配置",sameWindow=false,missing=false)=>{
      const targetAttr=sameWindow?"":" target=\"_blank\" rel=\"noopener noreferrer\"";
      const link=href?`<a class="preview-card-link" href="${href}"${targetAttr}>${esc(linkLabel)}</a>`:"";
      const display=missing&&href?`<a class="ro-config-link" href="${esc(href)}">${esc(value||"未配置")}</a>`:esc(value||"未配置");
      return `<div class="preview-card"><img src="/static/project_ui/svg/${icon}.svg" alt=""><div><span>${esc(label)}</span><strong>${display}</strong>${detail?`<small>${esc(detail)}</small>`:""}${link}</div></div>`;
    };
    const isMissingConfigValue=(value)=>!value||value==="未配置"||value==="管线未配置"||value==="尚未登记";
    const resolveMissingPipelineSection=(pipeline={},jenkins={})=>{
      if(!String(jenkins.jenkins_instance_id||"").trim())return "jenkins";
      if(!String(jenkins.jenkins_job_id||jenkins.jenkins_job||"").trim())return "jenkins";
      if(!(pipeline.config_export||{}).enabled)return "config_export";
      if(!(pipeline.resource_build||{}).enabled)return "resource_build";
      if(!(pipeline.hot_release||{}).enabled)return "hot_release";
      if(!(pipeline.apk_build||{}).enabled)return "artifact";
      return "jenkins";
    };
    const setSummaryField=(cell,value,href)=>{
      if(!cell)return;
      const text=String(value||"").trim()||"未配置";
      if(isMissingConfigValue(text)&&href){
        cell.innerHTML=`<a class="ro-config-link" href="${esc(href)}">${esc(text)}</a>`;
      }else{
        cell.textContent=text;
      }
    };
    const formatPipelinePillLabel=(readiness)=>{
      if(!readiness||typeof readiness!=="object"){
        return {label:"待配置：Jenkins 实例、Jenkins Job、管线四步",isReady:false};
      }
      const status=String(readiness.status||"").trim();
      const missingSteps=Array.isArray(readiness.missing_pipeline_steps)?readiness.missing_pipeline_steps:[];
      const missing=Array.isArray(readiness.missing)?readiness.missing:[];
      const checks=readiness.checks||{};
      const infraMissing=missing.filter((x)=>x==="Jenkins 实例"||x==="Jenkins Job");
      if(status==="ready"||(!status&&readiness.ready&&!missingSteps.length)){
        return {label:"版本组管线模板",isReady:true};
      }
      let stepMissing=missingSteps.length?missingSteps:missing.filter((x)=>!["Jenkins 实例","Jenkins Job","管线四步配置"].includes(x));
      let parts=[...infraMissing,...stepMissing];
      if(!parts.length){
        if(checks.jenkins_instance===false)parts.push("Jenkins 实例");
        if(checks.jenkins_job===false)parts.push("Jenkins Job");
        if(checks.pipeline===false)parts.push("管线四步配置");
      }
      if(!parts.length){
        if(readiness.ready)return {label:"版本组管线模板",isReady:true};
        if(String(readiness.blocker_hint||"").trim()){
          const hint=String(readiness.blocker_hint).trim();
          return {label:hint.startsWith("待")?hint:`待完善：${hint}`,isReady:false};
        }
        return {label:"待完善：请检查版本组管线模板",isReady:false};
      }
      const prefix=status==="unconfigured"&&!checks.jenkins_instance&&!checks.jenkins_job&&!checks.pipeline?"待配置":"待完善";
      return {label:`${prefix}：${parts.join("、")}`,isReady:false};
    };
    const setSourcePill=(pillEl,readiness,href)=>{
      if(!pillEl)return;
      const {label,isReady}=formatPipelinePillLabel(readiness);
      pillEl.classList.toggle("ready",isReady);
      pillEl.classList.toggle("missing",!isReady);
      if(!isReady&&href){
        pillEl.innerHTML=`<a class="ro-config-link" href="${esc(href)}">${esc(label)}</a>`;
      }else{
        pillEl.textContent=label;
      }
      const hintEl=document.getElementById("orderPipelineStatusHint");
      if(hintEl){
        hintEl.textContent="";
        hintEl.hidden=true;
      }
    };
    const buildLocalPipelineReadiness=(version)=>{
      if(!version||(!version.id&&!version.version_name))return null;
      const cached=effectivePipelineCache.get(version.id);
      if(cached?.readiness)return cached.readiness;
      const pipeline=version.pipeline&&typeof version.pipeline==="object"?version.pipeline:{};
      const stepDefs=[
        ["config_export","配置导出"],
        ["resource_build","资源打包"],
        ["hot_release","热更发布"],
        ["apk_build","安装包"],
      ];
      const jenkinsInstance=String(version.jenkins_instance_id||form.jenkins_instance_id?.value||"").trim();
      const jenkinsJob=String(version.jenkins_job_id||version.jenkins_job||form.jenkins_job?.value||"").trim();
      const enabledSteps=stepDefs.filter(([key])=>Boolean((pipeline[key]||{}).enabled));
      const missingSteps=stepDefs.filter(([key])=>!(pipeline[key]||{}).enabled).map(([,label])=>label);
      const hasPipeline=enabledSteps.length>0;
      const checks={
        jenkins_instance:Boolean(jenkinsInstance),
        jenkins_job:Boolean(jenkinsJob),
        pipeline:hasPipeline,
      };
      const missing=[];
      if(!checks.jenkins_instance)missing.push("Jenkins 实例");
      if(!checks.jenkins_job)missing.push("Jenkins Job");
      if(!checks.pipeline)missing.push("管线四步配置");
      else if(missingSteps.length)missing.push(...missingSteps);
      const ready=Object.values(checks).every(Boolean);
      let status="partial";
      if(!checks.jenkins_instance&&!checks.jenkins_job&&!checks.pipeline)status="unconfigured";
      else if(ready&&!missingSteps.length)status="ready";
      return {
        ready,
        status,
        checks,
        missing,
        missing_pipeline_steps:hasPipeline?missingSteps:stepDefs.map(([,label])=>label),
        jenkins_instance_id:jenkinsInstance,
        jenkins_job_id:jenkinsJob,
        pipeline_summary:enabledSteps.map(([,label])=>label).join(" · "),
        source:"local",
      };
    };
    let lastPipelineConfigHref="";
    const refreshPipelineSourcePill=(readinessOverride=null,hrefOverride="")=>{
      const pillEl=document.getElementById("orderPipelineSourcePill");
      if(!pillEl)return;
      const version=selectedVersion();
      const readiness=readinessOverride
        ||formContext.delivery_readiness?.pipeline
        ||buildLocalPipelineReadiness(version);
      const href=(readiness&&readiness.ready)?"":(hrefOverride||formContext.build_config_href||lastPipelineConfigHref||"");
      setSourcePill(pillEl,readiness,href);
    };
    const lockTargetFields=()=>{
      [form.env_key,form.channel_id,form.platform,form.version_id].forEach((field)=>{
        field.classList.add("is-locked");
        field.setAttribute("aria-readonly","true");
        field.tabIndex=-1;
      });
      const banner=document.getElementById("orderTargetLockBanner");
      if(banner)banner.classList.remove("is-hidden");
    };
    const applyTargetFromUrl=()=>{
      if(orderId)return false;
      const vn=search.get("version_name");
      const vc=search.get("version_code");
      const vid=search.get("version_id");
      if(!vn&&!vc&&!vid)return false;
      ["env_key","channel_id","platform"].forEach((key)=>{if(search.get(key))form[key].value=search.get(key);});
      renderVersions();
      let match=null;
      if(vid)match=options.versions.find((item)=>String(item.id)===String(vid));
      if(!match&&vn){
        match=options.versions.find((item)=>
          String(item.version_name||"")===vn
          &&(!vc||String(item.version_code||"")===vc)
          &&String(item.env_key||"")===String(form.env_key.value||"")
          &&String(item.channel_id||"")===String(form.channel_id.value||"")
          &&String(item.platform||"")===String(form.platform.value||""),
        );
      }
      if(match)form.version_id.value=match.id;
      lockTargetFields();
      renderPlanPreview();
      return Boolean(match||vn||vc||vid);
    };
    const loadEffectivePipeline=async(vid)=>{
      if(!vid)return null;
      if(effectivePipelineCache.has(vid))return effectivePipelineCache.get(vid);
      try{
        const data=await api(`/api/projects/${projectId}/versions/${encodeURIComponent(vid)}/effective-pipeline`);
        effectivePipelineCache.set(vid,data);
        return data;
      }catch(_e){return null;}
    };
    const renderPlanPreview=()=>{
      const version=selectedVersion();
      const ctx=versionContextQuery(version);
      const pipeline=version.pipeline&&typeof version.pipeline==="object"?version.pipeline:{};
      const apkBuild=pipeline.apk_build||{};
      const configExport=pipeline.config_export||{};
      const resourceBuild=pipeline.resource_build||{};
      const hotRelease=pipeline.hot_release||{};
      const pipelineSummary=[
        configExport.enabled?"配置导出":"",
        resourceBuild.enabled?"资源打包":"",
        hotRelease.enabled?"热更发布":"",
        apkBuild.enabled?"安装包":"",
      ].filter(Boolean).join(" · ")||"管线未配置";
      const buildConfigParams=new URLSearchParams();
      buildConfigParams.set("from","release-order");
      if(orderId)buildConfigParams.set("release_order_id",orderId);
      const ctxQs=versionContextQuery(version);
      if(ctxQs)new URLSearchParams(ctxQs).forEach((v,k)=>buildConfigParams.set(k,v));
      const anchorId=version.id||search.get("version_id")||"";
      const buildConfigBase=anchorId?`/admin/projects/${projectId}/versions/${encodeURIComponent(anchorId)}/build-config`:"";
      const buildConfigHref=(section)=>{
        if(!buildConfigBase)return "";
        buildConfigParams.set("section",section);
        return `${buildConfigBase}?${buildConfigParams.toString()}`;
      };
      const workflowHref=version.id?`/admin/projects/${projectId}/versions/${encodeURIComponent(version.id)}/workflow`:"";
      const buildHistoryHref=ctx?`/admin/projects/${projectId}/build-history?${ctx}`:`/admin/projects/${projectId}/build-history`;
      const jenkinsInstance=version.jenkins_instance_id||form.jenkins_instance_id.value;
      const jenkinsJob=version.jenkins_job_id||version.jenkins_job||form.jenkins_job.value;
      const jenkinsHref=jenkinsInstance?`/admin/jenkins/edit?instance_id=${encodeURIComponent(jenkinsInstance)}`:"/admin/jenkins";
      const jenkinsConfigHref=buildConfigHref("jenkins");
      const pipelineConfigHref=buildConfigHref(resolveMissingPipelineSection(pipeline,{jenkins_instance_id:jenkinsInstance,jenkins_job_id:jenkinsJob}));
      lastPipelineConfigHref=formContext.build_config_href||pipelineConfigHref||jenkinsConfigHref;
      const buildLinks={jenkinsInstance:jenkinsConfigHref,jenkinsJob:jenkinsConfigHref,pipeline:pipelineConfigHref||jenkinsConfigHref};
      const summaryCard=document.getElementById("orderPipelineSummaryCard");
      if(summaryCard){
        const instCell=summaryCard.querySelector("[data-field='jenkins_instance_id']");
        const jobCell=summaryCard.querySelector("[data-field='jenkins_job']");
        const pipelineCell=summaryCard.querySelector("[data-field='pipeline_summary']");
        setSummaryField(instCell,jenkinsInstance||"未配置",!jenkinsInstance?jenkinsConfigHref:"");
        setSummaryField(jobCell,jenkinsJob||"未配置",!jenkinsJob?jenkinsConfigHref:"");
        setSummaryField(pipelineCell,pipelineSummary,isMissingConfigValue(pipelineSummary)?pipelineConfigHref:"");
        refreshPipelineSourcePill(null,lastPipelineConfigHref);
        const cta=document.getElementById("orderGoConfigurePipelineBtn");
        if(cta){
          const href=formContext.build_config_href||jenkinsConfigHref;
          if(href){cta.href=href;cta.removeAttribute("hidden");}
          else cta.setAttribute("hidden","");
        }
      }
      const resourceReady=version.resource_url||version.resource_path||version.config_url||version.config_path;
      const artifactReady=version.apk_url||version.apk_path||version.apk_status==="found";
      updateJenkinsDisplay(version,buildLinks);
      document.getElementById("buildPlanPreview").innerHTML=[
        previewCard("nav_build_artifact","Jenkins 实例",jenkinsInstance||"未配置","维护 Jenkins 实例连接",!jenkinsInstance?jenkinsConfigHref:jenkinsHref,!jenkinsInstance?"去配置实例":"管理实例",!jenkinsInstance,!jenkinsInstance),
        previewCard("nav_execute","构建任务",jenkinsJob||"未配置","Job 与四步开关在版本组管线模板维护",jenkinsConfigHref,"配置版本组模板",true,!jenkinsJob),
        previewCard("nav_download_center","管线摘要",pipelineSummary,"配置导出、资源打包与热更",pipelineConfigHref,"配置管线",true,isMissingConfigValue(pipelineSummary)),
        previewCard("file_android","APK 产物",artifactReady?"已登记":"尚未登记","查看构建历史与产物",buildHistoryHref,"查看产物",false,!artifactReady),
      ].join("");
      const miniSummary=document.getElementById("orderMinimalBuildSummary");
      if(miniSummary){
        miniSummary.innerHTML=`<div class="minimal-build-banner"><strong>构建与管线（只读）</strong><p>${esc(pipelineSummary||"管线未配置")} · Jenkins ${esc(jenkinsInstance||"未配置")} / ${esc(jenkinsJob||"未配置")}</p>${formContext.build_config_href?`<a class="preview-card-link" href="${esc(formContext.build_config_href)}">配置版本组模板</a>`:""}</div>`;
      }
      if(!form.jenkins_instance_id.value&&version.jenkins_instance_id)form.jenkins_instance_id.value=version.jenkins_instance_id;
      if(!form.jenkins_job.value&&(version.jenkins_job||version.jenkins_job_id))form.jenkins_job.value=version.jenkins_job||version.jenkins_job_id;
      loadFormContext(version);
      if(version.id){
        loadEffectivePipeline(version.id).then((data)=>{
          if(!data)return;
          const card=document.getElementById("orderPipelineSummaryCard");
          if(!card)return;
          const eff=data.effective_pipeline||{};
          const summary=[
            (eff.config_export||{}).enabled?"配置导出":"",
            (eff.resource_build||{}).enabled?"资源打包":"",
            (eff.hot_release||{}).enabled?"热更发布":"",
            (eff.apk_build||{}).enabled?"安装包":"",
          ].filter(Boolean).join(" · ")||"管线未配置";
          const j=data.jenkins||{};
          const effBuildConfigHref=(section)=>{
            const base=data.build_config_href||buildConfigBase;
            if(!base)return "";
            const params=new URLSearchParams(buildConfigParams);
            params.set("section",section);
            return `${base.split("?")[0]}?${params.toString()}`;
          };
          const effJenkinsHref=effBuildConfigHref("jenkins");
          const effPipelineHref=effBuildConfigHref(resolveMissingPipelineSection(eff,j));
          lastPipelineConfigHref=data.build_config_href||effPipelineHref||effJenkinsHref||lastPipelineConfigHref;
          const readiness=data.readiness||{};
          const pillHref=readiness.ready?"":lastPipelineConfigHref;
          if(readiness&&typeof readiness==="object"){
            formContext.delivery_readiness=formContext.delivery_readiness||{};
            formContext.delivery_readiness.pipeline_ready=Boolean(readiness.ready);
            formContext.delivery_readiness.pipeline={...readiness};
            if(readiness.checks){
              formContext.delivery_readiness.checks={
                ...(formContext.delivery_readiness.checks||{}),
                ...readiness.checks,
              };
            }
            if(data.build_config_href)formContext.build_config_href=data.build_config_href;
          }
          refreshPipelineSourcePill(readiness,pillHref);
          updateCompleteness();
          setSummaryField(card.querySelector("[data-field='jenkins_instance_id']"),j.jenkins_instance_id||"未配置",!j.jenkins_instance_id?effJenkinsHref:"");
          setSummaryField(card.querySelector("[data-field='jenkins_job']"),j.jenkins_job_id||"未配置",!j.jenkins_job_id?effJenkinsHref:"");
          setSummaryField(card.querySelector("[data-field='pipeline_summary']"),summary,isMissingConfigValue(summary)?effPipelineHref:"");
          if(data.build_config_href){
            const cta=document.getElementById("orderGoConfigurePipelineBtn");
            if(cta){cta.href=data.build_config_href;cta.removeAttribute("hidden");}
          }
          updateJenkinsDisplay(version,{jenkinsInstance:effJenkinsHref,jenkinsJob:effJenkinsHref,pipeline:effPipelineHref});
          const instInput=form.jenkins_instance_id;
          const jobInput=form.jenkins_job;
          if(instInput&&j.jenkins_instance_id)instInput.value=j.jenkins_instance_id;
          if(jobInput&&j.jenkins_job_id)jobInput.value=j.jenkins_job_id;
        }).catch(()=>{});
      }
    };
    const renderVersions=()=>{
      const current=form.version_id.value;
      const items=options.versions.filter(x=>x.env_key===form.env_key.value&&x.channel_id===form.channel_id.value&&x.platform===form.platform.value);
      form.version_id.innerHTML=items.length?items.map(x=>`<option value="${esc(x.id)}">${esc(x.version_name)} / ${esc(x.version_code)}</option>`).join(""):'<option value="">当前目标暂无可用 VersionCode</option>';
      if(items.some(x=>String(x.id)===String(current)))form.version_id.value=current;
      renderPlanPreview();
    };
    const updateCompleteness=()=>{
      const required=formContext.required_fields||["env_key","channel_id","platform","version_id","reason","owner"];
      const planComplete=required.filter(key=>form[key]&&String(form[key].value||"").trim()).length;
      const planPercent=required.length?Math.round(planComplete/required.length*100):0;
      document.getElementById("planCompleteness").textContent=`${planPercent}%`;
      document.getElementById("planCompletenessBar").style.width=`${planPercent}%`;
      const delivery=formContext.delivery_readiness||{};
      const delPercent=Number(delivery.percent||0);
      const delEl=document.getElementById("deliveryReadiness");
      const delBar=document.getElementById("deliveryReadinessBar");
      if(delEl)delEl.textContent=`${delPercent}%`;
      if(delBar)delBar.style.width=`${delPercent}%`;
      updatePipelineGate();
      updateRuntimeStats();
      updateFormJourney();
      const readinessPanel=document.getElementById("orderReadinessPanel");
      if(readinessPanel)readinessPanel.classList.toggle("is-hidden",!form.version_id.value);
    };
    [form.env_key,form.channel_id,form.platform].forEach(x=>x.addEventListener("change",()=>{renderVersions();loadFormContext(selectedVersion());updateRiskPanel();const prod=document.getElementById("orderProductionBanner");if(prod)prod.classList.toggle("is-hidden",form.env_key.value!=="production");}));
    const prodBanner=document.getElementById("orderProductionBanner");if(prodBanner&&form.env_key.value==="production")prodBanner.classList.remove("is-hidden");
    form.version_id.addEventListener("change",()=>{renderPlanPreview();loadFormContext(selectedVersion());updateRiskPanel();});
    form.release_strategy?.addEventListener("change",()=>{syncGrayFieldVisibility();updateRiskPanel();});
    ["gray_strategy","gray_ratio","gray_duration","gray_success_action"].forEach((name)=>{
      form[name]?.addEventListener("input",syncGrayFieldVisibility);
      form[name]?.addEventListener("change",syncGrayFieldVisibility);
    });
    form.target_audience?.addEventListener("change",updateRiskPanel);
    form.addEventListener("input",updateCompleteness);
    syncGrayFieldVisibility();

    if(orderId){
      const order=await api(`/api/projects/${projectId}/release-orders/${orderId}`);
      ["env_key","channel_id","platform"].forEach(key=>form[key].value=order[key]);
      renderVersions();
      form.version_id.value=order.version_id;
      form.reason.value=order.reason||"";
      Object.entries(order.payload||{}).forEach(([key,value])=>{if(form[key])form[key].value=valueText(value);});
      if(form.target_topology_id&&order.payload?.target_topology_id)form.target_topology_id.value=order.payload.target_topology_id;
      document.getElementById("resolvedTopology").textContent=order.topology_id||"尚未解析";
      document.getElementById("resolvedRuntime").textContent=order.runtime_run_id||"预检后确认";
      lockTargetFields();
      renderPlanPreview();
      loadFormContext(selectedVersion());
    }else if(!applyTargetFromUrl()){
      ["env_key","channel_id","platform"].forEach((key)=>{if(search.get(key))form[key].value=search.get(key);});
      renderVersions();
      loadFormContext(selectedVersion());
      if(!orderId){
        try{
          const raw=localStorage.getItem(draftKey);
          if(raw){
            const draft=JSON.parse(raw);
            Object.entries(draft||{}).forEach(([key,val])=>{if(form[key]&&String(form[key].value||"").trim()==="")form[key].value=String(val??"");});
            page.querySelectorAll("[data-tag-field]").forEach((input)=>input.dispatchEvent(new Event("input",{bubbles:true})));
            syncDescCount();
            touchAutosave(true);
          }
        }catch(_e){/* ignore bad draft */}
      }
    }
    updateRiskPanel();
    updateCompleteness();
    const payload=()=>{
      const data=Object.fromEntries(new FormData(form).entries());
      ["env_key","channel_id","platform","version_id"].forEach((key)=>{
        if(form[key]?.classList.contains("is-locked"))data[key]=form[key].value;
      });
      return data;
    };
    const save=async(buildAfter=false)=>{
      try{
        if(buildAfter&&!formContext.delivery_readiness?.pipeline_ready){
          toast("管线未就绪，请先配置版本组管线模板","error");
          return;
        }
        if(!form.reportValidity())return;
        page.querySelectorAll("[data-save-order],[data-form-next]").forEach(button=>button.disabled=true);
        let order;
        if(orderId)order=await api(`/api/projects/${projectId}/release-orders/${orderId}`,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        else order=await api(`/api/projects/${projectId}/release-orders`,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify(payload())});
        document.getElementById("orderSaveStatus").textContent="草稿已保存";
        toast("发布单计划已保存");
        try{localStorage.removeItem(draftKey);}catch(_e){}
        touchAutosave(true);
        const context=buildScopeQuery({env_key:order.env_key,channel_id:order.channel_id,platform:order.platform,version_id:order.version_id,version_name:order.version_name,version_code:order.version_code,release_order_id:order.release_order_id});
        if(buildAfter){
          const artifactsReady=Boolean(formContext.delivery_readiness?.checks?.artifacts);
          if(artifactsReady){
            await api(`/api/projects/${projectId}/release-orders/${order.release_order_id}/precheck`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
          }else{
            await api(`/api/projects/${projectId}/release-orders/${order.release_order_id}/build`,{method:"POST",headers:{"Content-Type":"application/json"},body:"{}"});
          }
          location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}${context}`;
        }else if(!orderId)location.href=`/admin/projects/${projectId}/release-orders/${order.release_order_id}/edit${context}`;
      }catch(error){toast(error.message,"error");}
      finally{page.querySelectorAll("[data-save-order],[data-form-next]").forEach(button=>button.disabled=false);}
    };
    page.querySelector("[data-save-order]").addEventListener("click",()=>save(false));
    page.querySelector("[data-form-next]")?.addEventListener("click",()=>save(true));
  }
  global.DeliveryOrderForm = { setupOrderForm };
})(window);
