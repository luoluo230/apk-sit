
var _pd=(function(){var el=document.getElementById("project-detail-data");return el?JSON.parse(el.textContent):{};})();
function _normalizeProjectId(raw){
    var v = (raw == null ? '' : String(raw)).trim();
    if(!v) return '';
    if((v[0] === '"' && v[v.length-1] === '"') || (v[0] === "'" && v[v.length-1] === "'")){
        v = v.slice(1, -1).trim();
    }
    if(v === '""' || v === "''") v = '';
    return v;
}
function _projectIdFromPath(){
    try{
        var p = String(location.pathname || '');
        var marker = '/admin/projects/';
        var idx = p.indexOf(marker);
        if(idx < 0) return '';
        var rest = p.slice(idx + marker.length);
        var seg = rest.split('/')[0] || '';
        return seg ? decodeURIComponent(seg) : '';
    }catch(_e){
        return '';
    }
}
var PROJECT_ID=_normalizeProjectId(_pd.project_id)||_projectIdFromPath()||"";
var CAN_EDIT=_pd.can_edit||false;
// 快捷操作模块管理
var _projectModules={build_general:true,build_commercial:true};
function toggleModuleConfig(){var p=document.getElementById("moduleConfigPanel");if(!p)return;p.classList.toggle("hidden");if(!p.classList.contains("hidden"))renderModuleConfig();}
function renderModuleConfig(){var el=document.getElementById("moduleConfigList");if(!el)return;
var mods=[];
el.innerHTML=mods.map(function(m){var a=_projectModules[m.id];
return '<div class="flex items-center justify-between py-1 px-2 rounded-lg '+(a?"bg-amber-50":"bg-slate-50")+'">'+
'<span class="flex items-center gap-1.5"><i class="fas '+m.icon+' text-'+m.color+'-500"></i>'+m.label+'</span>'+
'<span>'+(a?'<span class="text-amber-600">✓ 已添加</span> <span class="module-remove" onclick="removeModule(&#39;'+m.id+'&#39;)">×</span>':'<button onclick="addModule(&#39;'+m.id+'&#39;)" class="text-[10px] text-indigo-500 hover:text-indigo-700">+ 添加</button>')+'</span></div>';
}).join("");}
function addModule(id){_projectModules[id]=true;renderModuleConfig();updateQuickActions();}
function removeModule(id){_projectModules[id]=false;renderModuleConfig();updateQuickActions();}
function updateQuickActions(){}
var _versionMode = 'general';
var _ppTargets = { code: true, resource: true };
function toggleCommercialMode() {
    var cb = document.getElementById('chkCommercialMode');
    _versionMode = cb.checked ? 'commercial' : 'general';
    var pp = document.getElementById('versionPipeline');
    if(pp) pp.classList.toggle('hidden', !cb.checked);
    var pipelineTabBtn = document.getElementById('versionPipelineTabBtn');
    if (pipelineTabBtn) {
        pipelineTabBtn.style.display = cb.checked ? '' : 'none';
    }
    if (!cb.checked) {
        switchVersionModalTab('identity');
    }
    var label = document.getElementById('labelCommercialMode');
    if(label) label.className = 'flex items-center gap-2.5 px-3 py-2 rounded-lg border-2 cursor-pointer transition-all ' + (cb.checked ? 'border-violet-500 bg-violet-50 shadow-sm shadow-violet-100' : 'border-slate-200 hover:border-violet-300');
}
function switchVersionModalTab(tab) {
    var panelMap = {identity:'vmTabIdentity', package:'vmTabPackage', release:'vmTabRelease', pipeline:'vmTabPipeline'};
    if (tab === 'pipeline' && _versionMode !== 'commercial') tab = 'identity';
    document.querySelectorAll('#versionMainTabs [data-vtab]').forEach(function(btn) {
        var key = btn.getAttribute('data-vtab');
        var active = btn.getAttribute('data-vtab') === tab;
        btn.className = 'flex-1 px-2.5 py-1.5 rounded-md text-xs font-semibold transition ' + (active ? 'bg-white text-indigo-700 shadow-sm' : 'text-slate-600 hover:bg-white/70');
        if (key === 'pipeline') {
            btn.style.display = (_versionMode === 'commercial') ? '' : 'none';
        }
    });
    Object.keys(panelMap).forEach(function(k) {
        var panel = document.getElementById(panelMap[k]);
        if (panel) panel.classList.toggle('hidden', k !== tab);
    });
}
function stageToReleaseEnvironment(stage) {
    var s = String(stage || 'dev').toLowerCase();
    if (s === 'production' || s === 'prod') return 'Production';
    if (s === 'staging' || s === 'stage') return 'Staging';
    if (s === 'test' || s === 'testing') return 'Testing';
    return 'Development';
}
function mapVersionChannelToReleaseChannel(channelId) {
    var key = String(channelId || '').trim();
    if (!key) return 'common';
    var info = CHANNELS_FULL && CHANNELS_FULL[key];
    if (info) {
        var bp = String(info.build_param || '').trim();
        if (bp) {
            var m = bp.match(/CHANNEL\\s*=\\s*([A-Za-z0-9_.-]+)/i);
            if (m && m[1]) return m[1];
            if (!/^\\d+$/.test(bp)) return bp;
        }
        var sub = String(info.apk_subdir || '').trim();
        if (sub && !/^\\d+$/.test(sub)) return sub;
    }
    if (!/^\\d+$/.test(key)) return key;
    return key || 'common';
}
function switchPipelineTab(tab) {
    document.querySelectorAll('#pipelineTabs [data-ptab]').forEach(function(b) {
        var isActive = b.getAttribute('data-ptab') === tab;
        b.className = 'flex-1 py-1.5 px-2 rounded text-xs font-medium transition ' + (isActive ? 'bg-indigo-600 text-white shadow-sm' : 'text-slate-500 hover:bg-white/60');
        var numSpan = b.querySelector('span');
        if(numSpan) numSpan.className = 'w-5 h-5 inline-flex items-center justify-center rounded-full text-[10px] font-bold mr-1 ' + (isActive ? 'bg-indigo-100 text-indigo-600' : 'bg-slate-200 text-slate-500');
    });
    document.querySelectorAll('.pipeline-panel').forEach(function(p) { p.classList.add('hidden'); });
    var panelMap = {config_export:'ptabConfigExport',resource_build:'ptabResourceBuild',hot_release:'ptabHotRelease',apk_build:'ptabApkBuild'};
    var panel = document.getElementById(panelMap[tab]);
    if(panel) panel.classList.remove('hidden');
}
function togglePipelineStep(step) {
    setTimeout(function(){ togglePipelineStepUI(step); }, 50);
}
function togglePipelineStepUI(step) {
    var cbs = {config_export:'ppConfigExportBody',resource_build:'ppResourceBuildBody',hot_release:'ppHotReleaseBody',apk_build:'ppApkBuildBody'};
    var ck = {config_export:'ppConfigExport',resource_build:'ppResourceBuild',hot_release:'ppHotRelease',apk_build:'ppApkBuild'};
    var cb = document.getElementById(ck[step]);
    var body = document.getElementById(cbs[step]);
    if(body && cb) body.classList.toggle('hidden', !cb.checked);
}
function togglePpChip(k){ _ppTargets[k]=!_ppTargets[k]; updatePpChips(); }
function updatePpChips(){
    var cs={code:['ppChipCode','bg-blue-100 text-blue-700 border-blue-300','bg-slate-100 text-slate-400 border-slate-200'],
        resource:['ppChipResource','bg-emerald-100 text-emerald-700 border-emerald-300','bg-slate-100 text-slate-400 border-slate-200']};
    Object.keys(cs).forEach(function(k){
        var c=cs[k], el=document.getElementById(c[0]);
        if(el) el.className='inline-flex items-center gap-1 px-3 py-1 rounded-full text-xs font-medium border-2 cursor-pointer select-none '+(_ppTargets[k]?c[1]:c[2]);
    });
    var codeCard=document.getElementById('ppStratCode');
    var resCard=document.getElementById('ppStratResource');
    if(codeCard) codeCard.style.display=_ppTargets.code?'':'none';
    if(resCard) resCard.style.display=_ppTargets.resource?'':'none';
    var codeEn=document.getElementById('ppHrCodeEnabled');
    var resEn=document.getElementById('ppHrResEnabled');
    if(codeEn) codeEn.checked=_ppTargets.code;
    if(resEn) resEn.checked=_ppTargets.resource;
}
function onPpHrModeChange(){
    var m=document.getElementById('ppHrMode').value;
    var rb=document.getElementById('ppHrRollback');
    if(rb) rb.disabled = m!=='rollback';
}
function collectPipeline() {
    var p = {};
    var stageEl = document.getElementById('versionStage');
    var releaseEnv = stageToReleaseEnvironment(stageEl ? stageEl.value : 'dev');
    var cfgPrefixEl = document.getElementById('ppCfgPrefix');
    var cfgPrefix = cfgPrefixEl ? String(cfgPrefixEl.value || '').trim() : '';
    cfgPrefix = cfgPrefix.replace(new RegExp('^/+|/+$', 'g'), '');
    if (cfgPrefixEl) cfgPrefixEl.value = cfgPrefix;
    var ce = document.getElementById('ppConfigExport');
    p.config_export = {
        enabled: ce ? ce.checked : false,
        environment: releaseEnv,
        platform: document.getElementById('versionPlatform').value,
        client_version: document.getElementById('ppCfgClientVer').value.trim(),
        remote_prefix: cfgPrefix,
        include_code: document.getElementById('ppCfgIncludeCode').checked
    };
    var rbCb = document.getElementById('ppResourceBuild');
    p.resource_build = {
        enabled: rbCb ? rbCb.checked : false,
        provider: document.getElementById('ppResProvider').value,
        scenario: document.getElementById('ppResScenario').value.trim()
    };
    var hrCb = document.getElementById('ppHotRelease');
    p.hot_release = {
        enabled: hrCb ? hrCb.checked : false,
        release_targets: Object.keys(_ppTargets).filter(function(k){return _ppTargets[k];}).join(','),
        release_mode: document.getElementById('ppHrMode').value,
        release_environment: releaseEnv,
        release_channel: mapVersionChannelToReleaseChannel(document.getElementById('versionChannel').value),
        release_hot_labels: document.getElementById('ppHrLabels').value.trim(),
        release_upload_mode: document.getElementById('ppHrUpload').value,
        release_rollback_target: document.getElementById('ppHrRollback').value.trim(),
        release_compression_override: document.getElementById('ppHrCompOvr').value,
        release_encryption_override: document.getElementById('ppHrEncOvr').value,
        release_signature_override: document.getElementById('ppHrSigOvr').value,
        code_enabled: document.getElementById('ppHrCodeEnabled').checked,
        code_compression: document.getElementById('ppHrCodeComp').value,
        code_encryption: document.getElementById('ppHrCodeEnc').value,
        code_signature: document.getElementById('ppHrCodeSig').value,
        code_units: document.getElementById('ppHrCodeUnits').value.trim(),
        resource_enabled: document.getElementById('ppHrResEnabled').checked,
        resource_compression: document.getElementById('ppHrResComp').value,
        resource_encryption: document.getElementById('ppHrResEnc').value,
        resource_signature: document.getElementById('ppHrResSig').value,
        resource_units: document.getElementById('ppHrResUnits').value.trim()
    };
    var abCb = document.getElementById('ppApkBuild');
    var releaseBranch = document.getElementById('ppApkBranch').value.trim();
    p.apk_build = {
        enabled: abCb ? abCb.checked : false,
        unity_version: document.getElementById('ppApkUnity').value.trim(),
        git_branch: releaseBranch,
        app_name: document.getElementById('ppApkAppName').value.trim(),
        output_base_dir: document.getElementById('ppApkOutput').value.trim()
    };
    if (releaseBranch) p.git_branch = releaseBranch;
    return p;
}
function validateCommercialPipeline(p) {
    if (!p || typeof p !== 'object') return '商业流水线参数无效';
    var hr = p.hot_release || {};
    if (hr.enabled) {
        var raw = String(hr.release_targets || '').trim().toLowerCase();
        if (!raw) return '热更发布已启用时，必须至少选择一个发布对象（代码包或资源包）';
        var arr = raw.split(',').map(function(x){ return x.trim(); }).filter(Boolean);
        var allowed = { code: true, resource: true };
        var uniq = [];
        for (var i = 0; i < arr.length; i++) {
            var t = arr[i];
            if (!allowed[t]) return '发布对象仅允许 code、resource，禁止 config 或其他值';
            if (uniq.indexOf(t) < 0) uniq.push(t);
        }
        if (uniq.length === 0) return '热更发布对象不能为空';
        hr.release_targets = uniq.join(',');
    }
    return '';
}
function restorePipeline(pipeline) {
    if(!pipeline) return;
    var restoreCfg = function(s, cb, body, fields) {
        if(!s) return;
        if(cb) cb.checked = !!s.enabled;
        if(body && cb) body.classList.toggle('hidden', !cb.checked);
        if(fields) fields.forEach(function(f) {
            var el = document.getElementById(f.id);
            if(el && s[f.key] !== undefined) {
                if(el.type==='checkbox') el.checked = !!s[f.key];
                else el.value = s[f.key] || '';
            }
        });
    };
    var ce = pipeline.config_export;
    restoreCfg(ce, document.getElementById('ppConfigExport'), document.getElementById('ppConfigExportBody'), [
        {id:'ppCfgClientVer',key:'client_version'},{id:'ppCfgPrefix',key:'remote_prefix'},
        {id:'ppCfgIncludeCode',key:'include_code'}
    ]);
    var rb = pipeline.resource_build;
    restoreCfg(rb, document.getElementById('ppResourceBuild'), document.getElementById('ppResourceBuildBody'), [
        {id:'ppResProvider',key:'provider'},{id:'ppResScenario',key:'scenario'}
    ]);
    var hr = pipeline.hot_release;
    if(hr) {
        restoreCfg(hr, document.getElementById('ppHotRelease'), document.getElementById('ppHotReleaseBody'), [
            
            {id:'ppHrLabels',key:'release_hot_labels'},{id:'ppHrMode',key:'release_mode'},
            {id:'ppHrUpload',key:'release_upload_mode'},{id:'ppHrRollback',key:'release_rollback_target'},
            {id:'ppHrCompOvr',key:'release_compression_override'},{id:'ppHrEncOvr',key:'release_encryption_override'},
            {id:'ppHrSigOvr',key:'release_signature_override'},
            {id:'ppHrCodeEnabled',key:'code_enabled'},{id:'ppHrCodeComp',key:'code_compression'},
            {id:'ppHrCodeEnc',key:'code_encryption'},{id:'ppHrCodeSig',key:'code_signature'},
            {id:'ppHrCodeUnits',key:'code_units'},
            {id:'ppHrResEnabled',key:'resource_enabled'},{id:'ppHrResComp',key:'resource_compression'},
            {id:'ppHrResEnc',key:'resource_encryption'},{id:'ppHrResSig',key:'resource_signature'},
            {id:'ppHrResUnits',key:'resource_units'}
        ]);
        if(hr.release_targets) {
            _ppTargets = {code:false,resource:false};
            hr.release_targets.split(',').forEach(function(t){ t=t.trim(); if(_ppTargets.hasOwnProperty(t)) _ppTargets[t]=true; });
            updatePpChips();
        }
        onPpHrModeChange();
    }
    var ab = pipeline.apk_build;
    if (ab && !ab.git_branch && pipeline.git_branch) ab.git_branch = pipeline.git_branch;
    restoreCfg(ab, document.getElementById('ppApkBuild'), document.getElementById('ppApkBuildBody'), [
        {id:'ppApkUnity',key:'unity_version'},{id:'ppApkBranch',key:'git_branch'},
        {id:'ppApkAppName',key:'app_name'},{id:'ppApkOutput',key:'output_base_dir'}
    ]);
    if (!document.getElementById('ppApkBranch').value && pipeline.git_branch) {
        document.getElementById('ppApkBranch').value = pipeline.git_branch;
    }
}
var CHANNELS_FULL=_pd.channels_full||{};
var PROJECT_CHANNELS=_pd.project_channels||[];
var ALL_CHANNELS=_pd.all_channels||[];
var VERSION_STAGES=_pd.version_stages||[{id:'dev',name:'开发'},{id:'test',name:'测试'},{id:'production',name:'线上'}];
var PROJECT_NAME_EN=(_pd.project_name_en||PROJECT_ID||'').replace(new RegExp("\\\\s","g"),"");
var STAGE_DIR_MAP={dev:'dev',test:'test',production:'release'};
var allVersions=(_pd.versions||[]).map(function(v){v.channel_label=v.channel_label||v.channel;v.stage=v.stage||'dev';v.stage_label=v.stage_label||'开发';return v;});
function _esc(s){if(s==null||s===undefined)return"";return String(s).replace(/&/g,"&amp;").replace(/</g,"&lt;").replace(/>/g,"&gt;").replace(/"/g,"&quot;");}
var VERSION_STATUS_META={
    draft:{label:'草稿',badge:'bg-slate-100 text-slate-700 border border-slate-200',row:'bg-slate-50/30',panel:'bg-slate-50/40'},
    active:{label:'有效',badge:'bg-emerald-100 text-emerald-700 border border-emerald-200',row:'bg-emerald-50/35',panel:'bg-emerald-50/45'},
    testing:{label:'测试中',badge:'bg-sky-100 text-sky-700 border border-sky-200',row:'bg-sky-50/35',panel:'bg-sky-50/45'},
    disabled:{label:'失效',badge:'bg-rose-100 text-rose-700 border border-rose-200',row:'bg-rose-50/35',panel:'bg-rose-50/45'},
    archived:{label:'归档',badge:'bg-slate-200 text-slate-700 border border-slate-300',row:'bg-slate-100/65',panel:'bg-slate-100/75'}
};
function normalizeVersionStatus(s){
    s=String(s||'').toLowerCase().trim();
    if(s==='draft') return 'draft';
    if(s==='valid'||s==='enabled'||s==='online') return 'active';
    if(s==='test'||s==='beta') return 'testing';
    if(s==='deprecated'||s==='obsolete'||s==='invalid'||s==='inactive') return 'disabled';
    if(s==='archive') return 'archived';
    return VERSION_STATUS_META[s] ? s : 'active';
}
function getVersionStatusMeta(s){
    return VERSION_STATUS_META[normalizeVersionStatus(s)] || VERSION_STATUS_META.active;
}
function _getVersionFilterKey(channelId, stageId){
    return String(channelId||'') + '::' + String(stageId||'');
}
function _getVersionFilter(channelId, stageId){
    window._versionFilters = window._versionFilters || {};
    var key = _getVersionFilterKey(channelId, stageId);
    if(!window._versionFilters[key]){
        window._versionFilters[key] = { q:'', platform:'all', status:'all' };
    }
    return window._versionFilters[key];
}

window.switchTab=function switchTab(name){
    var allowed={overview:1,channels:1,build:1,download:1};
    name = String(name||'overview').toLowerCase().trim();
    if(!allowed[name]) name='overview';
    document.querySelectorAll('.tab-btn').forEach(function(b){ b.classList.remove('text-amber-600','border-b-2','border-amber-600'); b.classList.add('text-gray-500'); });
    document.querySelectorAll('.tab-panel').forEach(function(p){ p.classList.add('hidden'); });
    var btn = document.getElementById('tab' + name.charAt(0).toUpperCase() + name.slice(1));
    var panel = document.getElementById('panel' + name.charAt(0).toUpperCase() + name.slice(1));
    if(btn){ btn.classList.remove('text-gray-500'); btn.classList.add('text-amber-600','border-b-2','border-amber-600'); }
    if(panel){ panel.classList.remove('hidden'); }
    if(name==='channels'){
        try{ renderChannelsView(); }catch(e){ console.error('renderChannelsView failed', e); alert('版本页面初始化失败，请刷新后重试。'); }
        var sec=document.getElementById('projectTabSection');
        if(sec){ sec.scrollIntoView({behavior:'smooth', block:'start'}); }
    }
    if(typeof history!=='undefined'&&history.replaceState){ var u=new URL(window.location.href); u.searchParams.set('tab',name); history.replaceState(null,'',u.pathname+u.search); }
};
function loadProjectRecentBuilds(){
    var el=document.getElementById('projectRecentBuilds'); if(!el) return;
    fetch('/api/build/recent?limit=5', {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        var builds=d.builds||[];
        if(builds.length===0){ el.innerHTML='<li class="text-slate-500">暂无构建记录，请先启动 Jenkins 并前往构建页</li>'; return; }
        var statusCls=function(r){ r=(r||'').toUpperCase(); if(r==='SUCCESS') return 'bg-green-100 text-green-800'; if(r==='FAILURE'||r==='ABORTED') return 'bg-red-100 text-red-800'; if(r==='UNSTABLE') return 'bg-yellow-100 text-yellow-800'; return 'bg-gray-100 text-gray-700'; };
        el.innerHTML=builds.map(function(b){ var badge='<span class="ml-1 px-2 py-0.5 rounded text-xs '+statusCls(b.result)+'">'+(b.result||'中')+'</span>'; return '<li><a href="/admin/projects/'+PROJECT_ID+'/build" class="text-indigo-600 hover:underline">#'+b.number+'</a> '+badge+'</li>'; }).join('');
    }).catch(function(){ el.innerHTML='<li class="text-slate-500">加载失败</li>'; });
}
window._showQR=function(filename){
    var modal=document.getElementById('projectQRModal'); var box=document.getElementById('projectQRCode');
    if(!modal||!box) return;
    box.innerHTML='<p class="text-slate-400 text-sm">加载中…</p>';
    modal.classList.remove('hidden'); modal.classList.add('flex');
    fetch('/qr/'+encodeURIComponent(filename),{credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        box.innerHTML= d.qr_code ? '<img src="'+d.qr_code+'" alt="QR" class="w-48 h-48 object-contain rounded-lg">' : '<p class="text-red-500 text-sm">加载失败</p>';
    }).catch(function(){ box.innerHTML='<p class="text-red-500 text-sm">加载失败</p>'; });
};
function _renderApkDownloadPanel(info){
    if(!info||!info.available){ return '<p class="text-slate-500 text-sm py-4">该版本暂无可下载的安装包</p>'; }
    var row=function(label,val){ return '<div class="flex gap-2 py-1"><span class="text-slate-400 w-20 shrink-0">'+label+'</span><span class="text-slate-800 break-all flex-1">'+val+'</span></div>'; };
    var qrBlock=function(title,url,qr){
        if(!url) return '';
        var img=qr?'<img src="'+qr+'" alt="QR" class="w-36 h-36 object-contain rounded-lg border border-slate-100 bg-white p-1">':'<p class="text-slate-400 text-xs">无二维码</p>';
        return '<div class="rounded-xl border border-slate-200 p-4 bg-slate-50/50"><p class="text-xs font-semibold text-slate-600 mb-2">'+title+'</p>'+img+'<p class="text-[11px] text-slate-500 mt-2 break-all">'+_esc(url)+'</p><a href="'+_esc(url)+'" target="_blank" rel="noopener" class="inline-flex mt-2 text-indigo-600 text-xs hover:underline">打开链接</a></div>';
    };
    var html='<div class="space-y-4">';
    html+=row('构建时间',_esc(info.build_time||'—'));
    html+=row('包名',_esc(info.package_name||info.app_name||'—'));
    html+=row('文件',_esc(info.file_name||'—'));
    html+=row('大小',_esc(info.size_label||'—'));
    html+=row('渠道/阶段',_esc((info.channel_label||info.channel||'-')+' / '+(info.stage_label||info.stage||'-')));
    html+='<div class="grid md:grid-cols-2 gap-4 pt-2">';
    html+=qrBlock('本地下载',info.local_download_url,info.local_qr_dataurl);
    html+=qrBlock('远端下载',info.oss_download_url,info.oss_qr_dataurl);
    html+='</div>';
    if(info.pub_download_path){ html+='<div class="pt-2"><a href="/pub/download/'+_esc(info.pub_download_path)+'" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700"><i class="fas fa-download"></i>直接下载</a></div>'; }
    html+='</div>';
    return html;
}
function openVersionDownloadsModal(vid){
    var modal=document.getElementById('versionDownloadsModal'); var list=document.getElementById('versionDownloadsList');
    if(!modal||!list) return;
    list.innerHTML='<p class="text-slate-400 text-sm">加载中…</p>';
    modal.classList.remove('hidden'); modal.classList.add('flex');
    fetch('/api/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/'+encodeURIComponent(vid)+'/apk-download-info', {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        if(d.error&&!d.available){ list.innerHTML='<p class="text-slate-500 text-sm py-4">'+_esc(d.error||'暂无可下载的安装包')+'</p>'; return; }
        list.innerHTML=_renderApkDownloadPanel(d);
    }).catch(function(){ list.innerHTML='<p class="text-red-500 text-sm">加载失败</p>'; });
}
(function(){
    var h=window.location.hash;
    var qTab=(new URLSearchParams(window.location.search)).get('tab');
    if(qTab){ switchTab(qTab); }
    else if(h&&h.indexOf('tab=')>=0){ var m=h.match(/tab=([a-z]+)/); if(m) switchTab(m[1]); }
    else { switchTab('overview'); }
    fetch('/api/projects/'+encodeURIComponent(PROJECT_ID)+'/download-stats', {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
        var el=document.getElementById('projectTrend7d'); if(el) el.textContent = (d.sum_7d!=null) ? '最近7日：'+d.sum_7d+' 次' : '—';
    }).catch(function(){});
})();
document.addEventListener('click', function(e){
    var link = e.target.closest('a[href*="?tab=channels"]');
    if(!link) return;
    try{
        var u = new URL(link.href, window.location.origin);
        if(u.pathname === window.location.pathname){
            e.preventDefault();
            switchTab('channels');
        }
    }catch(_err){}
});

window._versionBuildState = window._versionBuildState || {};
window._versionBuildStateLoading = false;
window._versionBuildStateTimer = window._versionBuildStateTimer || null;
function _isVersionBuilding(versionId){
    if(!window._versionBuildState || typeof window._versionBuildState !== 'object'){
        window._versionBuildState = {};
    }
    var st = window._versionBuildState[String(versionId||'')] || {};
    return !!st.building;
}
function refreshVersionBuildState(){
    if(window._versionBuildStateLoading) return;
    if(!window._versionBuildState || typeof window._versionBuildState !== 'object'){
        window._versionBuildState = {};
    }
    var ids = (allVersions||[]).map(function(v){ return String(v.id||'').trim(); }).filter(Boolean);
    if(!ids.length){ window._versionBuildState = {}; return; }
    window._versionBuildStateLoading = true;
    Promise.all(ids.map(function(id){
        return fetch('/api/build/history-by-version?version_id='+encodeURIComponent(id), {credentials:'same-origin'})
            .then(function(r){ return r.json(); })
            .then(function(d){
                var builds = (d&&d.builds) ? d.builds : [];
                if(!builds.length) return [id, {building:false, build_number:null}];
                var sorted = builds.slice().sort(function(a,b){ return (parseInt(b.number||0,10)||0) - (parseInt(a.number||0,10)||0); });
                var latest = sorted[0] || {};
                var latestNo = parseInt(latest.number||0,10)||null;
                var building = !!latest.building || String(latest.result||'').toUpperCase()==='BUILDING' || String(latest.result||'').toUpperCase()==='QUEUED';
                return [id, {building: building, build_number: latestNo}];
            })
            .catch(function(){ return [id, {building:false, build_number:null}]; });
    })).then(function(rows){
        var next = {};
        rows.forEach(function(row){ next[row[0]] = row[1]; });
        var prev = JSON.stringify(window._versionBuildState||{});
        var curr = JSON.stringify(next);
        window._versionBuildState = next;
        if(prev !== curr) renderChannelsView();
    }).finally(function(){
        window._versionBuildStateLoading = false;
    });
}
function ensureVersionBuildStateTimer(){
    if(window._versionBuildStateTimer) return;
    window._versionBuildStateTimer = setInterval(refreshVersionBuildState, 5000);
}

function renderChannelsView(){
    var wrap = document.getElementById('channelsVersionsWrap');
    var empty = document.getElementById('channelsEmpty');
    if(!wrap) return;
    var chs = PROJECT_CHANNELS || [];
    var stages = VERSION_STAGES || [{id:'dev',name:'开发'},{id:'test',name:'测试'},{id:'production',name:'线上'}];
    if(chs.length===0){ wrap.innerHTML=''; if(empty) empty.classList.remove('hidden'); return; }
    if(empty) empty.classList.add('hidden');
    var activeChannelId = (window._activeChannelId || (chs[0] && chs[0].id) || '');
    var activeChannel = null;
    for(var ci=0; ci<chs.length; ci++){
        if((chs[ci].id||'') === activeChannelId){ activeChannel = chs[ci]; break; }
    }
    if(!activeChannel){ activeChannel = chs[0]; activeChannelId = activeChannel.id || ''; }
    window._activeChannelId = activeChannelId;

    var html = '<div class="channel-card bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">';
    html += '<div class="px-5 py-4 bg-gradient-to-r from-slate-50 to-white border-b border-slate-100">';
    html += '<div class="text-sm font-semibold text-slate-800 mb-3 flex items-center gap-2"><i class="fas fa-layer-group text-indigo-500"></i>发布渠道</div>';
    html += '<div class="flex flex-wrap gap-2">';
    for(var ti=0; ti<chs.length; ti++){
        var t = chs[ti]; var tid = t.id||''; var tname = t.name||tid; var on = tid===activeChannelId;
        html += '<button type="button" class="channel-main-tab px-3.5 py-1.5 rounded-lg text-sm font-medium transition '+(on?'bg-indigo-600 text-white shadow-sm':'bg-slate-100 text-slate-700 hover:bg-slate-200')+'" data-channel-id="'+_esc(tid)+'">'+_esc(tname)+'</button>';
    }
    html += '</div></div>';

    var cid = activeChannel.id||'';
    html += '<div class="px-5 py-3 border-b border-slate-50 flex flex-wrap justify-between items-center gap-2">';
    html += '<span class="text-xs text-slate-500 shrink-0">当前渠道：'+_esc(activeChannel.name||cid)+'</span>';
    html += '<div class="flex items-center gap-2 ml-auto flex-wrap">';
    html += '<div class="flex rounded-lg bg-slate-100/80 p-0.5">';
    for(var s=0;s<stages.length;s++){
        var st = stages[s]; var sid = st.id||'dev'; var sname = st.name||'开发'; var isFirst = s===0;
        html += '<button type="button" class="channel-stage-tab px-3.5 py-1.5 text-xs font-medium rounded-md transition '+(isFirst?'bg-white text-slate-800 shadow-sm':'text-slate-600 hover:text-slate-800')+'" data-block="channel-tabs" data-stage="'+_esc(sid)+'">'+_esc(sname)+'</button>';
    }
    html += '</div>';
    html += '<div class="flex items-center gap-2 shrink-0">';
    if(CAN_EDIT) html += '<button type="button" data-channel-id="'+_esc(cid)+'" class="ch-open-version-btn-main px-3 py-1.5 rounded-lg text-xs font-medium bg-indigo-600 text-white hover:bg-indigo-700 shadow-sm transition"><i class="fas fa-plus text-[10px] mr-1"></i>新建版本</button>';
    html += '<a href="/admin/projects/'+PROJECT_ID+'/build-history" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-emerald-600 text-white hover:bg-emerald-700 shadow-sm transition inline-flex items-center"><i class="fas fa-history text-[10px] mr-1"></i>构建历史</a>';
    if(CAN_EDIT) html += '<button type="button" onclick="openDeviceManageModal()" class="px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-700 text-white hover:bg-slate-800 shadow-sm transition inline-flex items-center"><i class="fas fa-mobile-alt text-[10px] mr-1"></i>设备管理</button>';
    html += '</div></div></div>';

    for(var s2=0;s2<stages.length;s2++){
        var st2 = stages[s2]; var sid2 = st2.id||'dev'; var sname2 = st2.name||'开发';
        var versAllChannel = allVersions.filter(function(v){ return ((v.channel||'').toLowerCase()===(cid||'').toLowerCase()); });
        var f = _getVersionFilter(cid, sid2);
        var kw = String(f.q||'').toLowerCase().trim();
        var fPlatform = String(f.platform||'all').toLowerCase();
        var fStatusRaw = String(f.status||'all').toLowerCase();
        var fStatus = (fStatusRaw==='all') ? 'all' : normalizeVersionStatus(fStatusRaw);
        var versFiltered = versAllChannel.filter(function(v){
            var okName = !kw || String(v.version_name||'').toLowerCase().indexOf(kw) >= 0 || String(v.version_code||'').toLowerCase().indexOf(kw) >= 0;
            var okPlatform = (fPlatform==='all') || (String(v.platform||'').toLowerCase()===fPlatform);
            var okStatus = (fStatus==='all') || (normalizeVersionStatus(v.version_status||'active')===fStatus);
            return okName && okPlatform && okStatus;
        });
        var vers = versFiltered.filter(function(v){ return (v.stage||'dev')===(sid2||'dev'); });
        var versAll = versAllChannel;
        var panelHidden = s2>0 ? ' hidden' : '';
        html += '<div class="channel-stage-panel'+panelHidden+'" data-block="channel-tabs" data-stage="'+_esc(sid2)+'">';
        html += '<div class="px-5 py-3 flex justify-between items-center border-b border-slate-50">';
        html += '<span class="text-xs text-slate-500">'+_esc(sname2)+' 阶段 · 本阶段 '+vers.length+' 条 / 渠道内 '+versFiltered.length+' 条</span>';
        html += '</div><div class="p-5">';
        html += '<div class="mb-3 grid grid-cols-1 md:grid-cols-3 gap-2" data-version-filter-wrap="1">';
        html += '<input type="text" class="version-filter-input px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500" placeholder="筛选版本号 / Version Code" value="'+_esc(f.q||'')+'" data-channel-id="'+_esc(cid)+'" data-stage="'+_esc(sid2)+'" data-filter-field="q">';
        html += '<select class="version-filter-input px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500" data-channel-id="'+_esc(cid)+'" data-stage="'+_esc(sid2)+'" data-filter-field="platform">';
        html += '<option value="all"'+(fPlatform==='all'?' selected':'')+'>全部平台</option><option value="android"'+(fPlatform==='android'?' selected':'')+'>Android</option><option value="ios"'+(fPlatform==='ios'?' selected':'')+'>iOS</option>';
        html += '</select>';
        html += '<select class="version-filter-input px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500" data-channel-id="'+_esc(cid)+'" data-stage="'+_esc(sid2)+'" data-filter-field="status">';
        html += '<option value="all"'+(fStatus==='all'?' selected':'')+'>全部状态</option><option value="draft"'+(fStatus==='draft'?' selected':'')+'>草稿</option><option value="testing"'+(fStatus==='testing'?' selected':'')+'>测试中</option><option value="active"'+(fStatus==='active'?' selected':'')+'>有效</option><option value="disabled"'+(fStatus==='disabled'?' selected':'')+'>失效</option><option value="archived"'+(fStatus==='archived'?' selected':'')+'>归档</option>';
        html += '</select>';
        html += '</div>';
        if(vers.length===0){
            html += '<div class="py-10 text-center rounded-xl bg-slate-50/60 border border-dashed border-slate-200"><i class="fas fa-cube text-3xl text-slate-200 mb-2"></i><p class="text-slate-500 text-sm">没有匹配的版本</p><p class="text-slate-400 text-xs mt-0.5">'+(versAll.length>0?'试试调整筛选条件':'点击「新建版本」添加')+'</p></div>';
        } else {
            // ---- 按版本号分组（同渠道同 version_name 跨阶段归为一组）----
            var groups = {};
            versFiltered.forEach(function(v){
                var vn = (v.version_name || '').trim() || '未命名';
                if(!groups[vn]) groups[vn] = [];
                groups[vn].push(v);
            });
            var groupKeys = Object.keys(groups).sort(function(a,b){ return b.localeCompare(a); });
            html += '<div class="space-y-3">';
            for(var gi=0; gi<groupKeys.length; gi++){
                var gName = groupKeys[gi];
                var gVersAll = groups[gName];
                var gVers = gVersAll.filter(function(x){ return (x.stage||'dev')===(sid2||'dev'); });
                var activeCount = gVersAll.filter(function(x){ return normalizeVersionStatus(x.version_status||'active')==='active'; }).length;
                var totalDownloads = gVersAll.reduce(function(s,x){ return s + (x.download_count||0); }, 0);
                var stageCountHint = (gVers.length<gVersAll.length) ? ('（本阶段 '+gVers.length+' 个）') : '';
                var hasRecommended = gVers.some(function(x){ return x.recommended; });
                var hasCommercial = gVers.some(function(x){ return (x.version_mode||'general')==='commercial'; });
                var gStatusLabel = activeCount===gVersAll.length ? '全部有效' : (activeCount>0 ? activeCount+'/'+gVersAll.length+' 有效' : '全部非有效');
                var gStatusColor = activeCount===gVersAll.length ? 'bg-emerald-100 text-emerald-700' : (activeCount>0 ? 'bg-amber-100 text-amber-700' : 'bg-slate-100 text-slate-500');
                // 组级操作（编辑/删除第一个版本，或弹出批量操作）
                var firstV = gVersAll[0];
                var gActions = CAN_EDIT ? '<button type="button" data-version-name="'+_esc(gName)+'" class="version-add-code-btn version-op-btn version-op-build"><i class="fas fa-plus text-[10px]" style="pointer-events:none;"></i>增加 VersionCode</button><button type="button" data-version-id="'+_esc(firstV.id||'')+'" class="version-group-edit-btn version-op-btn version-op-edit"><i class="fas fa-pen text-[10px]" style="pointer-events:none;"></i>编辑版本</button><button type="button" data-version-name="'+_esc(gName)+'" class="version-group-delete-btn version-op-btn version-op-delete"><i class="fas fa-trash text-[10px]" style="pointer-events:none;"></i>删除组</button>' : '';
                var gRecBadge = hasRecommended ? ' <span class="px-1.5 py-0.5 rounded text-[10px] bg-amber-100 text-amber-700">推荐</span>' : '';
                var gModeBadge = hasCommercial ? ' <span class="px-1.5 py-0.5 rounded text-[10px] bg-violet-100 text-violet-700">🚀 商业版</span>' : ' <span class="px-1.5 py-0.5 rounded text-[10px] bg-slate-100 text-slate-500">📦 通用</span>';
                html += '<div class="version-group rounded-xl border overflow-hidden '+(hasCommercial?'border-violet-200 bg-violet-50/20':'border-slate-200 bg-white')+'" style="border-left:3px solid '+(hasCommercial?'#8b5cf6':'#cbd5e1')+';">';
                html += '<div class="version-group-header flex items-center justify-between px-4 py-3 bg-slate-50/60 cursor-pointer select-none" >';
                html += '<div class="flex items-center gap-2">';
                html += '<i class="fas fa-chevron-down text-[10px] text-slate-400 transition-transform version-group-arrow" style="pointer-events:none;"></i>';
                html += '<span class="font-semibold text-sm text-slate-800">'+_esc(gName)+gRecBadge+gModeBadge+'</span>';
                html += '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] '+gStatusColor+'">'+gStatusLabel+'</span>';
                html += '<span class="text-[11px] text-slate-400">'+gVersAll.length+' 个 VersionCode'+stageCountHint+' · '+totalDownloads+' 次下载</span>';
                html += '</div>';
                html += '<div class="flex items-center gap-2">' + gActions + '</div>';
                html += '</div>';
                // 子表
                html += '<div class="version-group-body">';
                html += '<table class="w-full text-xs"><thead><tr class="border-b border-slate-100 text-left text-slate-400"><th class="px-4 py-2 font-normal">Version Code</th><th class="px-4 py-2 font-normal">阶段</th><th class="px-4 py-2 font-normal">平台</th><th class="px-4 py-2 font-normal">状态</th><th class="px-4 py-2 font-normal">安装包</th><th class="px-4 py-2 font-normal">下载</th><th class="px-4 py-2 font-normal">路径</th><th class="px-4 py-2 font-normal w-28">操作</th></tr></thead><tbody>';
                if(!gVers.length && gVersAll.length){
                    html += '<tr><td colspan="8" class="px-4 py-4 text-center text-slate-500 text-xs">本阶段暂无 VersionCode，请切换到其他阶段标签查看，或在当前阶段点击「增加 VersionCode」</td></tr>';
                }
                for(var vj=0; vj<gVers.length; vj++){
                    var v = gVers[vj]; var vid = v.id||'';
                    var isBuilding = _isVersionBuilding(vid);
                    var stMeta = getVersionStatusMeta(v.version_status);
                    var stBadge = '<span class="inline-flex items-center px-2 py-0.5 rounded text-[10px] '+stMeta.badge+'">'+_esc(stMeta.label)+'</span>';
                    var apkBadge = (v.apk_status==='found') ? '<span class="text-[10px] text-emerald-600"><i class="fas fa-check-circle mr-0.5"></i>已落盘</span>' : ((v.apk_status==='not_found') ? '<span class="text-[10px] text-slate-400" style="display:block;line-height:1;margin-bottom:1px;">未找到</span>' : '—');
                    var buildCls = isBuilding ? 'text-amber-500 animate-pulse' : 'text-emerald-600 hover:text-emerald-800';
                    var buildIconCls = isBuilding ? 'fas fa-cogs fa-spin' : 'fas fa-cogs';
                    var buildTitle = isBuilding ? '构建中（仅可查看）' : '构建';
                    var vActions = '<a href="/admin/projects/'+PROJECT_ID+'/versions/'+_esc(vid)+'/workflow" class="'+buildCls+' text-[11px] mr-2" title="'+buildTitle+'"><i class="'+buildIconCls+'" style="pointer-events:none;"></i></a>';
                    if(v.apk_status==='found') vActions += '<button type="button" data-version-id="'+_esc(vid)+'" class="version-downloads-btn text-emerald-600 hover:text-emerald-800 text-[11px] mr-2" title="下载安装包"><i class="fas fa-download" style="pointer-events:none;"></i></button>';
                    if(CAN_EDIT && !isBuilding) vActions += '<button type="button" data-version-id="'+_esc(vid)+'" class="version-code-edit-btn text-indigo-500 hover:text-indigo-700 text-[11px] mr-2" title="编辑 VersionCode"><i class="fas fa-pen" style="pointer-events:none;"></i></button><button type="button" data-version-id="'+_esc(vid)+'" class="version-delete-btn text-rose-500 hover:text-rose-700 text-[11px]" title="删除"><i class="fas fa-trash" style="pointer-events:none;"></i></button>';
                    var rowBg = vj%2===0 ? 'bg-white' : 'bg-slate-50/30';
                    var isCommercialV = (v.version_mode||'general')==='commercial';
                    var vModeBg = isCommercialV ? '' : rowBg; var vModeStyle = isCommercialV ? 'background:linear-gradient(to right,#ede9fe,#f5f3ff);' : '';
                    var vModeIndicator = '';
                    var detailId = 'vd_'+_esc(vid);
                    // Build detail content
                    var dHtml = '<div class="grid grid-cols-3 gap-x-4 gap-y-1 text-xs">';
                    dHtml += '<div><span class="text-slate-400">渠道:</span> '+_esc(v.channel_label||v.channel||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">阶段:</span> '+_esc(v.stage_label||v.stage||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">平台:</span> '+_esc(v.platform_label||v.platform||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">版本名:</span> '+_esc(v.version_name||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">版本模式:</span> '+(isCommercialV?'<span class="text-violet-600 font-medium">商业版</span>':'<span class="text-slate-500">通用版</span>')+'</div>';
                    dHtml += '<div><span class="text-slate-400">发布方式:</span> '+_esc(v.distribution_method||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">包名:</span> '+_esc(v.package_name||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">最低SDK:</span> '+_esc(v.min_sdk||'-')+'</div>';
                    dHtml += '<div><span class="text-slate-400">Jenkins:</span> '+_esc(v.jenkins_job_id||'-')+'</div>';
                    dHtml += '<div class="col-span-3"><span class="text-slate-400">安装包:</span> '+_esc(v.apk_path||'-')+'</div>';
                    dHtml += '<div class="col-span-3"><span class="text-slate-400">资源路径:</span> '+_esc(v.resource_path||'-')+'</div>';
                    dHtml += '<div class="col-span-3"><span class="text-slate-400">配置路径:</span> '+_esc(v.config_path||'-')+'</div>';
                    if(v.changelog_text) dHtml += '<div class="col-span-3"><span class="text-slate-400">更新说明:</span> '+_esc(v.changelog_text)+'</div>';
                    if(v.notes) dHtml += '<div class="col-span-3"><span class="text-slate-400">备注:</span> '+_esc(v.notes)+'</div>';
                    if(isCommercialV && v.pipeline){
                        var pp = v.pipeline;
                        dHtml += '<div class="col-span-3 mt-1 pt-1 border-t border-slate-100"><span class="text-violet-600 font-medium">流水线参数</span></div>';
                        if(pp.config_export) dHtml += '<div class="col-span-3"><span class="text-slate-400">配置导出:</span> '+(pp.config_export.enabled?'启用':'禁用')+' | 前缀:'+_esc(pp.config_export.remote_prefix||'-')+' | 版本:'+_esc(pp.config_export.client_version||'-')+'</div>';
                        if(pp.resource_build) dHtml += '<div class="col-span-3"><span class="text-slate-400">资源打包:</span> '+(pp.resource_build.enabled?'启用':'禁用')+' | 引擎:'+_esc(pp.resource_build.provider||'-')+'</div>';
                        if(pp.hot_release){
                            var hr=pp.hot_release;
                            dHtml += '<div class="col-span-3"><span class="text-slate-400">热更发布:</span> '+(hr.enabled?'启用':'禁用')+' | 对象:'+_esc(hr.release_targets||'-')+' | 模式:'+_esc(hr.release_mode||'-')+' | 上传:'+_esc(hr.release_upload_mode||'-')+'</div>';
                            if(hr.code_enabled) dHtml += '<div class="col-span-3 pl-3"><span class="text-blue-500">代码包:</span> 压缩:'+_esc(hr.code_compression||'-')+' 加密:'+_esc(hr.code_encryption||'-')+' 签名:'+_esc(hr.code_signature||'-')+'</div>';
                            if(hr.resource_enabled) dHtml += '<div class="col-span-3 pl-3"><span class="text-emerald-500">资源包:</span> 压缩:'+_esc(hr.resource_compression||'-')+' 加密:'+_esc(hr.resource_encryption||'-')+' 签名:'+_esc(hr.resource_signature||'-')+'</div>';
                        }
                        if(pp.apk_build) dHtml += '<div class="col-span-3"><span class="text-slate-400">APK打包:</span> '+(pp.apk_build.enabled?'启用':'禁用')+'</div>';
                    dHtml += '<div class="col-span-3 mt-2 pt-2 border-t border-slate-200"><div class="flex items-center justify-between mb-2"><span class="text-slate-600 font-semibold text-xs"><i class="fas fa-history text-emerald-500 mr-1"></i>构建记录</span><a href="/admin/projects/'+PROJECT_ID+'/versions/'+_esc(vid)+'/workflow" class="text-indigo-600 hover:underline text-[11px]">去构建</a></div><div id="buildHist_'+vid+'" data-version-id="'+vid+'" class="build-history-panel"><p class="text-slate-400 text-[11px]">展开后加载…</p></div></div>';
                    }
                    dHtml += '</div>';
                    var colCount = 8;
                    
                    html += '<tr class="'+vModeBg+' '+stMeta.row+' border-b border-slate-50 hover:bg-slate-100/30 transition" style="'+vModeStyle+(isCommercialV?'border-left:3px solid #8b5cf6;':'')+'">';
                    html += '<td class="px-4 py-2 font-mono text-slate-700"><div class="flex items-center gap-1.5">'+_esc(v.version_code||'-')+vModeIndicator+'<button type="button" class="ver-expand-btn ml-1 text-slate-400 hover:text-slate-600" data-detail-id="'+detailId+'"><i class="fas fa-chevron-down text-[9px] ver-expand-arrow transition-transform" style="pointer-events:none;"></i></button></div></td>';
                    html += '<td class="px-4 py-2 text-slate-500">'+_esc(v.stage_label||v.stage||'-')+'</td>';
                    html += '<td class="px-4 py-2 text-slate-500">'+_esc(v.platform_label||v.platform||'-')+'</td>';
                    html += '<td class="px-4 py-2">'+stBadge+'</td>';
                    html += '<td class="px-4 py-2">'+apkBadge+'</td>';
                    var dlCell = '<span class="text-slate-500">'+(v.download_count||0)+'</span>';
                    html += '<td class="px-4 py-2">'+dlCell+'</td>';
                    html += '<td class="px-4 py-2 text-slate-400 max-w-[180px] truncate" title="'+_esc(v.apk_path||'')+'">'+_esc(v.apk_path||'-')+'</td>';
                    html += '<td class="px-4 py-2">'+vActions+'</td>';
                    html += '</tr>';
                    html += '<tr id="'+detailId+'" class="hidden"><td colspan="'+colCount+'" class="px-4 py-3" style="'+(isCommercialV?'background:#ede9fe;border-left:3px solid #8b5cf6;':'background:#f8fafc;border-left:3px solid #e2e8f0;')+'">'+dHtml+'</td></tr>';
                }
                html += '</tbody></table></div></div>';
            }
            html += '</div>';
        }
        html += '</div></div>';
    }
    html += '</div>';
    wrap.innerHTML = html;

    document.querySelectorAll('.channel-main-tab').forEach(function(btn){
        btn.onclick = function(){
            window._activeChannelId = btn.getAttribute('data-channel-id') || '';
            renderChannelsView();
        };
    });
    document.querySelectorAll('.channel-stage-tab').forEach(function(btn){
        btn.onclick = function(){
            var block = btn.getAttribute('data-block'); var stage = btn.getAttribute('data-stage');
            var card = document.querySelector('[data-block-id="'+block+'"]');
            if(!card) card = wrap;
            card.querySelectorAll('.channel-stage-tab').forEach(function(b){ b.classList.remove('bg-white','text-slate-800','shadow-sm'); b.classList.add('text-slate-600'); });
            btn.classList.add('bg-white','text-slate-800','shadow-sm'); btn.classList.remove('text-slate-600');
            card.querySelectorAll('.channel-stage-panel').forEach(function(p){ p.classList.add('hidden'); });
            var pan = card.querySelector('.channel-stage-panel[data-stage="'+stage+'"]'); if(pan) pan.classList.remove('hidden');
        };
    });
    // === 直接绑定事件（不依赖事件委托）===
    wrap.querySelectorAll('.version-group-header').forEach(function(header){
        header.onclick = function(e){
            if(e.target.closest('.version-op-btn')||e.target.closest('.version-group-delete-btn')) return;
            toggleVersionGroup(header);
        };
    });
    wrap.querySelectorAll('.version-group-delete-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            var vn=btn.getAttribute('data-version-name');
            if(vn&&requireDeleteConfirm('版本组: '+vn)){deleteVersionGroup(vn);}
        };
    });
    wrap.querySelectorAll('.version-group-edit-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            editVersion(btn.getAttribute('data-version-id'));
        };
    });
    wrap.querySelectorAll('.version-code-edit-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            openVersionCodeModal(btn.getAttribute('data-version-id'));
        };
    });
    wrap.querySelectorAll('.version-delete-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            deleteVersion(btn.getAttribute('data-version-id'));
        };
    });
    wrap.querySelectorAll('.ver-expand-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            toggleVerDetail(btn);
        };
    });
    wrap.querySelectorAll('.ch-open-version-btn-main').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            var chId=btn.getAttribute('data-channel-id')||'';
            var activeStageBtn=document.querySelector('.channel-stage-tab.bg-white');
            var stg=activeStageBtn?activeStageBtn.getAttribute('data-stage'):'dev';
            openVersionModal(chId,stg);
        };
    });
    wrap.querySelectorAll('.ch-open-version-btn').forEach(function(btn){
        btn.onclick = function(e){
            e.stopPropagation();
            openVersionModal(btn.getAttribute('data-channel-id')||'',btn.getAttribute('data-stage')||'dev');
        };
    });
}
(function(){
var _wrap = document.getElementById('channelsVersionsWrap');
if(!_wrap) return;
_wrap.addEventListener('click', function(e){
    var t=e.target.closest('.ch-open-version-btn-main');if(t){e.stopPropagation();var chId=t.getAttribute('data-channel-id')||''; var activeStageBtn=document.querySelector('.channel-stage-tab.bg-white'); var stg=activeStageBtn?activeStageBtn.getAttribute('data-stage'):'dev'; openVersionModal(chId,stg); return;}
    t=e.target.closest('.ch-open-version-btn');
    if(t){e.stopPropagation();openVersionModal(t.getAttribute('data-channel-id')||'',t.getAttribute('data-stage')||'dev');return;}
    t=e.target.closest('.ver-expand-btn');if(t){e.stopPropagation();toggleVerDetail(t);return;}
    t=e.target.closest('.version-fold-btn');if(t){e.stopPropagation();var vid=t.getAttribute('data-version-id'); var row=document.querySelector('.version-params-row[data-version-id="'+vid+'"]'); if(row){ row.classList.toggle('hidden'); t.querySelector('i').className=row.classList.contains('hidden')?'fas fa-chevron-down text-[10px]':'fas fa-chevron-up text-[10px]'; } return;}
    t=e.target.closest('.version-downloads-btn');if(t){e.stopPropagation();openVersionDownloadsModal(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.build-detail-btn');if(t){e.stopPropagation();openBuildDetailModal(t.getAttribute('data-instance-id'), t.getAttribute('data-build-number'), t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.build-del-btn');if(t){e.stopPropagation();deleteBuildRecord(t.getAttribute('data-instance-id'), t.getAttribute('data-build-number'), t.getAttribute('data-version-id'), t.getAttribute('data-container-id'));return;}
    t=e.target.closest('.version-group-edit-btn');if(t){e.stopPropagation();editVersion(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.version-code-edit-btn');if(t){e.stopPropagation();openVersionCodeModal(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.version-add-code-btn');if(t){e.stopPropagation();openAddVersionCodeModal(t.getAttribute('data-version-name'));return;}
    t=e.target.closest('.version-delete-btn');if(t){e.stopPropagation();deleteVersion(t.getAttribute('data-version-id'));return;}
    t=e.target.closest('.version-group-header');if(t&&!e.target.closest('.version-op-btn')&&!e.target.closest('.version-group-delete-btn')){e.stopPropagation();toggleVersionGroup(t);return;}
    t=e.target.closest('.version-group-delete-btn');if(t){e.stopPropagation();var vn=t.getAttribute('data-version-name');if(vn&&requireDeleteConfirm('版本组: '+vn)){deleteVersionGroup(vn);}}
}, true);
})();
function _buildStatusBadgeClass(result, building){
    if(building) return 'bg-amber-100 text-amber-800';
    var r=String(result||'').toUpperCase();
    if(r==='SUCCESS') return 'bg-green-100 text-green-800';
    if(r==='FAILURE'||r==='ABORTED') return 'bg-red-100 text-red-800';
    if(r==='UNSTABLE') return 'bg-yellow-100 text-yellow-800';
    return 'bg-gray-100 text-gray-700';
}
function loadVersionBuildHistory(versionId, containerId){
    var el=document.getElementById(containerId);
    if(!el||!versionId) return;
    el.innerHTML='<p class="text-slate-400 text-[11px]">加载中…</p>';
    fetch('/api/build/history-by-version?version_id='+encodeURIComponent(versionId), {credentials:'same-origin'})
    .then(function(r){ return r.json(); })
    .then(function(d){
        var builds=(d&&d.builds)||[];
        if(!builds.length){ el.innerHTML='<p class="text-slate-400 text-[11px]">暂无构建记录</p>'; return; }
        var html='<ul class="space-y-1.5">';
        builds.forEach(function(b){ html+=renderBuildHistoryItem(b, versionId); });
        html+='</ul>';
        el.innerHTML=html;
    })
    .catch(function(){ el.innerHTML='<p class="text-red-500 text-[11px]">加载失败</p>'; });
}
function renderBuildHistoryItem(b, versionId){
    var num=b.number||b.build_number||'-';
    var iid=String(b.instance_id||'');
    var result=b.result||(b.building?'BUILDING':'');
    var badgeCls=_buildStatusBadgeClass(result, !!b.building);
    var label=b.status_label||result||'未知';
    var who=b.triggered_by?' · '+_esc(b.triggered_by):'';
    var time=b.started_at?_esc(String(b.started_at).replace('T',' ').slice(0,19)):'';
    var delBtn='';
    if(CAN_EDIT && !b.building){
        delBtn='<button type="button" class="build-del-btn text-rose-500 hover:text-rose-700 text-[10px] ml-2 px-1" data-instance-id="'+_esc(iid)+'" data-build-number="'+num+'" data-version-id="'+_esc(versionId||'')+'" data-container-id="buildHist_'+_esc(versionId||'')+'" title="删除记录"><i class="fas fa-trash" style="pointer-events:none;"></i></button>';
    }
    return '<li class="flex items-center justify-between py-1 px-2 rounded-lg bg-white border border-slate-100 hover:border-slate-200">'
        +'<button type="button" class="build-detail-btn text-left flex-1 min-w-0" data-instance-id="'+_esc(iid)+'" data-build-number="'+num+'" data-version-id="'+_esc(versionId||'')+'">'
        +'<span class="text-indigo-600 font-mono font-medium">#'+num+'</span> '
        +'<span class="inline-block px-1.5 py-0.5 rounded text-[10px] font-medium '+badgeCls+'">'+_esc(label)+'</span>'
        +'<span class="text-[10px] text-slate-400 ml-1">'+time+who+'</span></button>'+delBtn+'</li>';
}
function openBuildDetailModal(instanceId, buildNumber, versionId){
    var modal=document.getElementById('buildDetailModal');
    var body=document.getElementById('buildDetailBody');
    if(!modal||!body) return;
    body.innerHTML='<p class="text-slate-400 text-sm">加载中…</p>';
    modal.classList.remove('hidden'); modal.classList.add('flex');
    var q='instance_id='+encodeURIComponent(instanceId)+'&version_id='+encodeURIComponent(versionId||'')+'&project_id='+encodeURIComponent(PROJECT_ID||'');
    fetch('/api/build/'+encodeURIComponent(buildNumber)+'/detail?'+q, {credentials:'same-origin'})
    .then(function(r){ return r.json(); })
    .then(function(d){
        if(d.error||!d.build){ body.innerHTML='<p class="text-red-500 text-sm">'+_esc(d.error||'加载失败')+'</p>'; return; }
        body.innerHTML=renderBuildDetailContent(d.build);
    })
    .catch(function(){ body.innerHTML='<p class="text-red-500 text-sm">加载失败</p>'; });
}
function _bdFoldBlock(title, bodyHtml, open){
    return '<details class="rounded-xl border border-slate-200 bg-white overflow-hidden mb-3"'+(open?' open':'')+'><summary class="flex items-center justify-between px-4 py-2.5 bg-slate-50/80 hover:bg-slate-50 select-none cursor-pointer"><span class="text-xs font-semibold text-slate-600">'+title+'</span><i class="fas fa-chevron-down text-slate-400 text-[10px]"></i></summary><div class="px-4 py-3 border-t border-slate-100">'+bodyHtml+'</div></details>';
}
function renderBuildDetailContent(b){
    var params=b.parameters||{};
    var keys=Object.keys(params);
    var paramRows=keys.map(function(k){
        return '<tr class="border-b border-slate-50"><td class="py-1 pr-3 text-slate-500 whitespace-nowrap align-top w-40">'+_esc(k)+'</td><td class="py-1 font-mono text-[11px] break-all">'+_esc(String(params[k]))+'</td></tr>';
    }).join('');
    var summary='';
    if(b.result==='SUCCESS'||b.status_label==='成功'){
        summary='<div class="rounded-lg bg-emerald-50 border border-emerald-100 p-3 text-sm text-emerald-800"><i class="fas fa-check-circle mr-1"></i>构建成功</div>';
    } else if(b.building){
        summary='<div class="rounded-lg bg-amber-50 border border-amber-100 p-3 text-sm text-amber-800"><i class="fas fa-spinner fa-spin mr-1"></i>构建进行中…</div>';
    } else if(b.failure_summary){
        summary='<div class="rounded-lg bg-red-50 border border-red-100 p-3 text-sm text-red-800 whitespace-pre-wrap">'+_esc(b.failure_summary)+'</div>';
    }
    var consoleBtn=b.console_url?'<a href="'+_esc(b.console_url)+'" target="_blank" rel="noopener" class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg bg-indigo-600 text-white text-xs hover:bg-indigo-700"><i class="fas fa-external-link-alt"></i>Jenkins 控制台</a>':'';
    var bn=b.number||b.build_number||'';
    var logUrl='/api/build/log/'+bn+'?instance_id='+encodeURIComponent(b.instance_id||'');
    var dlBtn='<a href="'+logUrl+'" download="build-'+bn+'.log" class="inline-flex items-center gap-1 px-3 py-1.5 rounded-lg border border-slate-200 text-slate-700 text-xs hover:bg-slate-50"><i class="fas fa-download"></i>下载日志</a>';
    var logPreview=(b.log||'').slice(-8000);
    var metaHtml='<div class="grid grid-cols-2 gap-x-4 gap-y-1 text-xs">'
        +'<div><span class="text-slate-400">构建号:</span> <span class="font-mono">#'+bn+'</span></div>'
        +'<div><span class="text-slate-400">状态:</span> '+_esc(b.status_label||b.result||'-')+'</div>'
        +'<div><span class="text-slate-400">构建人:</span> '+_esc(b.triggered_by||'-')+'</div>'
        +'<div><span class="text-slate-400">开始:</span> '+_esc((b.started_at||'').replace('T',' ').slice(0,19)||'-')+'</div>'
        +'<div><span class="text-slate-400">结束:</span> '+_esc(b.ended_at||'-')+'</div>'
        +'<div><span class="text-slate-400">用时:</span> '+_esc(b.duration||'-')+'</div>'
        +'</div>';
    var paramBody=paramRows?'<div class="max-h-56 overflow-auto"><table class="w-full text-xs">'+paramRows+'</table></div>':'<p class="text-slate-400 text-xs">无参数</p>';
    var logBody='<pre class="text-[10px] leading-relaxed bg-slate-900 text-slate-100 rounded-lg p-3 max-h-64 overflow-auto whitespace-pre-wrap">'+_esc(logPreview||'（无日志）')+'</pre>';
    return summary
        +'<div class="flex flex-wrap gap-2 mt-3">'+consoleBtn+dlBtn+'</div>'
        +_bdFoldBlock('基本信息', metaHtml, true)
        +(keys.length?_bdFoldBlock('构建参数 ('+keys.length+')', paramBody, false):'')
        +_bdFoldBlock('构建日志', logBody, false);
}
function deleteBuildRecord(instanceId, buildNumber, versionId, containerId){
    if(!window.confirm('确定删除构建 #'+buildNumber+'？将同时删除 Jenkins 构建目录，不可恢复。')) return;
    var q='instance_id='+encodeURIComponent(instanceId)+'&version_id='+encodeURIComponent(versionId||'')+'&project_id='+encodeURIComponent(PROJECT_ID||'');
    fetch('/api/build/'+encodeURIComponent(buildNumber)+'?'+q, {method:'DELETE', credentials:'same-origin', headers:{'Content-Type':'application/json'}, body:JSON.stringify({instance_id:instanceId})})
    .then(function(r){ return r.json(); })
    .then(function(d){
        if(!d.success){ alert(d.error||'删除失败'); return; }
        if(containerId) loadVersionBuildHistory(versionId, containerId);
    })
    .catch(function(){ alert('删除失败'); });
}
function toggleVerDetail(btn){
    var detailId = btn.getAttribute('data-detail-id');
    var d = document.getElementById(detailId);
    if(d){
        var opening = d.classList.contains('hidden');
        d.classList.toggle('hidden');
        if(opening){
            var panel = d.querySelector('.build-history-panel');
            if(panel) loadVersionBuildHistory(panel.getAttribute('data-version-id'), panel.id);
        }
    }
    var a = btn.querySelector('.ver-expand-arrow');
    if(a) a.classList.toggle('rotate-180');
}
function toggleVersionGroup(header){
    var group = header.closest('.version-group');
    var body = group ? group.querySelector('.version-group-body') : null;
    var arrow = header.querySelector('.version-group-arrow');
    if(body){ body.classList.toggle('hidden'); }
    if(arrow){ arrow.classList.toggle('fa-chevron-down'); arrow.classList.toggle('fa-chevron-up'); }
}
function requireDeleteConfirm(targetLabel){
    var tip = '删除后不可恢复。\\n请输入“删除”确认删除：\\n目标：' + (targetLabel || '当前项');
    var input = window.prompt(tip, '');
    return input && String(input).trim() === '删除';
}
function deleteVersionGroup(versionName){
    var ids = allVersions.filter(function(v){ return (v.version_name||'').trim()===versionName; }).map(function(v){ return v.id||''; }).filter(Boolean);
    if(!ids.length) return;
    var deleteNext = function(idx){
        if(idx>=ids.length){ renderChannelsView(); return; }
        var vid = ids[idx];
        fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/delete/'+encodeURIComponent(vid), { method:'DELETE', credentials:'same-origin' })
        .then(function(r){ return r.json(); })
        .then(function(d){
            if(!d || !d.error){
                allVersions = allVersions.filter(function(v){ return (v.id||'') !== vid; });
            }
            deleteNext(idx+1);
        })
        .catch(function(){ deleteNext(idx+1); });
    };
    deleteNext(0);
}
document.getElementById("channelsVersionsWrap")&&document.getElementById("channelsVersionsWrap").addEventListener("input",function(e){
    var el=e.target.closest(".version-filter-input");
    if(!el) return;
    var field=el.getAttribute("data-filter-field");
    var channelId=el.getAttribute("data-channel-id")||"";
    var stageId=el.getAttribute("data-stage")||"dev";
    if(!field) return;
    var f=_getVersionFilter(channelId, stageId);
    f[field]=el.value||"";
    renderChannelsView();
});
document.getElementById("channelsVersionsWrap")&&document.getElementById("channelsVersionsWrap").addEventListener("change",function(e){
    var el=e.target.closest(".version-filter-input");
    if(!el) return;
    var field=el.getAttribute("data-filter-field");
    var channelId=el.getAttribute("data-channel-id")||"";
    var stageId=el.getAttribute("data-stage")||"dev";
    if(!field) return;
    var f=_getVersionFilter(channelId, stageId);
    f[field]=el.value||"";
    renderChannelsView();
});
function toggleAddChannelDropdown(){
    var dd = document.getElementById('addChannelDropdown');
    if(!dd) return;
    if(dd.classList.contains('hidden')){ dd.classList.remove('hidden'); dd.innerHTML = ''; var cur = (PROJECT_CHANNELS||[]).map(function(c){ return (c.id||'').toLowerCase(); }); var opts = ALL_CHANNELS||[]; for(var i=0;i<opts.length;i++){ var o=opts[i]; if(cur.indexOf((o.id||'').toLowerCase())>=0) continue; dd.innerHTML += '<button type="button" data-channel-id='+JSON.stringify(o.id||'')+' class="add-channel-btn w-full text-left px-4 py-1.5 text-sm text-slate-700 hover:bg-slate-100">'+_esc(o.name||o.id)+'</button>'; } if(dd.innerHTML==='') dd.innerHTML='<p class="px-4 py-2 text-slate-500 text-sm">无更多渠道可添加</p>'; }
    else dd.classList.add('hidden');
}
document.addEventListener('click', function(e){ var dd=document.getElementById('addChannelDropdown'); var b=e.target.closest('.add-channel-btn'); if(b&&b.closest('#addChannelDropdown')){ addProjectChannel(b.dataset.channelId); if(dd) dd.classList.add('hidden'); return; } var rb=e.target.closest('.remove-channel-btn'); if(rb){ removeProjectChannel(rb.getAttribute('data-channel-id')||''); return; } if(dd&&!dd.classList.contains('hidden')&&!e.target.closest('.relative')) dd.classList.add('hidden'); });
function addProjectChannel(cid){ fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/channels/add', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({channel_id:cid}), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } location.reload(); }); }
function removeProjectChannel(cid){ if(!confirm('确定从项目中移除此渠道？该渠道下的版本将不再在渠道列表中显示。')) return; fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/channels/remove', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({channel_id:cid}), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } location.reload(); }); }

var _unityVersionCatalog=[];
function _setUnityVersionHint(text,isErr){
    var el=document.getElementById('ppApkUnityHint');
    if(!el) return;
    el.textContent=text||'';
    el.className='text-[10px] mt-0.5 '+(isErr?'text-rose-500':'text-slate-400');
}
function fetchUnityVersionCatalog(done){
    return fetch('/api/jenkins-manage/unity-catalog?active_only=1',{credentials:'same-origin'})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(function(d){
        var rows=(d&&d.entries)||[];
        _unityVersionCatalog=rows.map(function(e){ return {version:e.version,path:e.path,category:e.category,note:e.note}; });
        if(done) done(_unityVersionCatalog); return _unityVersionCatalog;
    })
    .catch(function(e){ _unityVersionCatalog=[]; _setUnityVersionHint('加载 Unity 版本库失败：'+(e&&e.message?e.message:'请先在 Jenkins 管理维护'),true); if(done) done([]); return []; });
}
function renderUnityVersionSelect(selected){
    var sel=document.getElementById('ppApkUnity');
    if(!sel) return;
    var want=String(selected||sel.value||'').trim();
    var items=_unityVersionCatalog||[];
    sel.innerHTML='';
    if(!items.length){
        var empty=document.createElement('option');
        empty.value=want;
        empty.textContent=want?('已保存: '+want):'暂无有效 Unity 版本';
        sel.appendChild(empty);
        _setUnityVersionHint('版本库中无有效项，请到 Jenkins 管理 → Unity 版本库 添加',true);
        return;
    }
    var i, v, op, label;
    for(i=0;i<items.length;i++){
        v=(items[i]&&items[i].version)||'';
        if(!v) continue;
        op=document.createElement('option');
        op.value=v;
        label=v;
        if(items[i]&&items[i].category){ label+=' ['+items[i].category+']'; }
        if(items[i]&&items[i].note){ label+=' - '+items[i].note; }
        op.textContent=label;
        sel.appendChild(op);
    }
    if(want){
        var found=false;
        for(i=0;i<sel.options.length;i++){ if(sel.options[i].value===want){ found=true; break; } }
        if(!found){
            op=document.createElement('option');
            op.value=want;
            op.textContent='（已保存·可能已失效）'+want;
            sel.insertBefore(op, sel.firstChild);
        }
        sel.value=want;
    } else if(sel.options.length){ sel.selectedIndex=0; }
    _setUnityVersionHint('已加载 '+items.length+' 个有效 Unity 版本',false);
}
function ensureUnityVersionSelect(selected,done){
    var sel=document.getElementById('ppApkUnity');
    if(sel){ sel.innerHTML='<option value="">加载中...</option>'; }
    _setUnityVersionHint('正在加载 Unity 版本库...',false);
    if(_unityVersionCatalog&&_unityVersionCatalog.length){
        renderUnityVersionSelect(selected);
        if(done) done();
        return;
    }
    fetchUnityVersionCatalog(function(){ renderUnityVersionSelect(selected); if(done) done(); });
}
document.getElementById('btnRefreshUnityVersions')&&document.getElementById('btnRefreshUnityVersions').addEventListener('click',function(){
    _unityVersionCatalog=[];
    ensureUnityVersionSelect((document.getElementById('ppApkUnity')||{}).value||'');
});
function buildDerivedVersionBasePath(versionCode){
    var ch=(document.getElementById('versionChannel')||{}).value||'common';
    var st=(document.getElementById('versionStage')||{}).value||'dev';
    var platform=((document.getElementById('versionPlatform')||{}).value||'android').toLowerCase();
    var vn=((document.getElementById('versionName')||{}).value||'1.0.0').trim()||'1.0.0';
    var stageMap={dev:'Development',test:'Testing',production:'Production'};
    var env=stageMap[st]||'Development';
    var channelSeg=mapVersionChannelToReleaseChannel(ch);
    var verFolder='Version_'+vn;
    var vc=String(versionCode||'').trim();
    var codeSeg=vc?('/'+vc):'';
    return env+'/'+channelSeg+'/'+platform+'/'+verFolder+codeSeg;
}
function syncDerivedVersionPaths(versionCode){
    var base=buildDerivedVersionBasePath(versionCode);
    var resEl=document.getElementById('versionResourcePath');
    var cfgEl=document.getElementById('versionConfigPath');
    if(resEl) resEl.value=base;
    if(cfgEl) cfgEl.value=base+'/config';
}
function suggestVersionApkPath(){ var ch=document.getElementById('versionChannel').value; var st=(document.getElementById('versionStage')||{}).value||'dev'; var platform=(document.getElementById('versionPlatform')||{}).value||'android'; var vn=(document.getElementById('versionName')||{}).value.trim()||'1.0.0'; var info=CHANNELS_FULL&&CHANNELS_FULL[ch]; var stageDir=STAGE_DIR_MAP[st]||'dev'; var ext=platform==='ios'?'.ipa':'.apk'; var pkgName=PROJECT_ID+'_'+vn.replace(new RegExp("\\\\s","g"),"")+ext; var sug; if(info&&info.apk_subdir){ sug=info.apk_subdir+'/'+stageDir+'/'+pkgName; } else { sug=stageDir+'/'+pkgName; } var apkEl=document.getElementById('versionApkPath'); if(apkEl&&!apkEl.value) apkEl.placeholder='建议: '+sug; }
function syncVersionPlatformFields(){ var platform=(document.getElementById('versionPlatform')||{}).value||'android'; var androidFields=document.getElementById('androidVersionFields'); var iosFields=document.getElementById('iosVersionFields'); var distribution=document.getElementById('versionDistributionMethod'); if(androidFields) androidFields.classList.toggle('hidden', platform==='ios'); if(iosFields) iosFields.classList.toggle('hidden', platform!=='ios'); if(distribution && !distribution.value){ distribution.value = platform==='ios' ? 'testflight' : 'direct'; } }
function setVersionCodeRuntimeCompatFormFields(v){
    var row=v||{};
    var vn=(row.version_name||'').trim();
    var minEl=document.getElementById('versionCodeMinClientVersion');
    var rolloutEl=document.getElementById('versionCodeRolloutPercentage');
    var revokedEl=document.getElementById('versionCodeIsRevoked');
    var minStored=(row.min_client_version||'').trim();
    if(minEl) minEl.value=(minStored&&vn&&minStored===vn)?'':minStored;
    if(rolloutEl) rolloutEl.value=(row.rollout_percentage!=null&&row.rollout_percentage!=='')?String(row.rollout_percentage):'100';
    if(revokedEl) revokedEl.checked=!!row.is_revoked;
}
function readVersionCodeRuntimeCompatPayload(fallbackVersionName){
    var vn=(fallbackVersionName||'').trim()||'1.0.0';
    var minEl=document.getElementById('versionCodeMinClientVersion');
    var rolloutEl=document.getElementById('versionCodeRolloutPercentage');
    var revokedEl=document.getElementById('versionCodeIsRevoked');
    var minV=minEl?(minEl.value||'').trim():'';
    var rollout=rolloutEl?parseInt(rolloutEl.value,10):100;
    if(isNaN(rollout)) rollout=100;
    rollout=Math.max(0, Math.min(100, rollout));
    return { min_client_version:minV||vn, max_client_version:vn, rollout_percentage:rollout, is_revoked:!!(revokedEl&&revokedEl.checked) };
}
function openDeviceManageModal(){ document.getElementById('deviceManageModal').classList.remove('hidden'); resetDeviceForm(); loadTestDevices(); }
function closeDeviceManageModal(){ document.getElementById('deviceManageModal').classList.add('hidden'); }
function resetDeviceForm(){ ['deviceEditId','deviceEditDeviceId','deviceEditLabel','deviceEditNotes'].forEach(function(id){ var e=document.getElementById(id); if(e) e.value=''; }); var p=document.getElementById('deviceEditPlatform'); if(p) p.value='android'; var s=document.getElementById('deviceEditStage'); if(s) s.value='dev'; }
function loadTestDevices(){
    var wrap=document.getElementById('deviceListWrap'); if(!wrap) return; wrap.textContent='加载中…';
    fetch('/api/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/test-devices',{credentials:'same-origin'}).then(function(r){return r.json();}).then(function(d){
        window._testDeviceRows=(d&&d.devices)?d.devices:[];
        if(!window._testDeviceRows.length){ wrap.innerHTML='<p class="text-slate-400 text-xs">暂无设备</p>'; return; }
        var stageMap={dev:'开发',test:'测试',production:'线上'}, html='<table class="w-full text-xs"><thead><tr class="text-slate-500 border-b"><th class="text-left py-1">设备ID</th><th class="text-left py-1">平台</th><th class="text-left py-1">阶段</th><th class="text-left py-1">备注</th><th class="text-right py-1">操作</th></tr></thead><tbody>';
        window._testDeviceRows.forEach(function(row, idx){
            html+='<tr class="border-b border-slate-100"><td class="py-1.5 font-mono text-[11px]">'+_esc(row.device_id||'')+'</td><td class="py-1.5">'+_esc(row.platform||'')+'</td><td class="py-1.5">'+_esc(stageMap[row.stage]||row.stage||'')+'</td><td class="py-1.5">'+_esc(row.label||row.notes||'-')+'</td><td class="py-1.5 text-right"><button type="button" class="text-indigo-600 hover:underline mr-2" data-idx="'+idx+'" onclick="editTestDeviceByIdx(this)">编辑</button><button type="button" class="text-rose-500 hover:underline" onclick="deleteTestDevice('+JSON.stringify(row.id||'')+')">删除</button></td></tr>';
        });
        wrap.innerHTML=html+'</tbody></table>';
    }).catch(function(){ wrap.textContent='加载失败'; });
}
function editTestDeviceByIdx(btn){ var row=(window._testDeviceRows||[])[parseInt(btn.getAttribute('data-idx')||'0',10)]; if(!row) return; document.getElementById('deviceEditId').value=row.id||''; document.getElementById('deviceEditDeviceId').value=row.device_id||''; document.getElementById('deviceEditPlatform').value=row.platform||'android'; document.getElementById('deviceEditStage').value=row.stage||'dev'; document.getElementById('deviceEditLabel').value=row.label||''; document.getElementById('deviceEditNotes').value=row.notes||''; }
function saveTestDevice(){
    var payload={ id:(document.getElementById('deviceEditId')||{}).value||'', device_id:((document.getElementById('deviceEditDeviceId')||{}).value||'').trim(), platform:((document.getElementById('deviceEditPlatform')||{}).value||'android'), stage:((document.getElementById('deviceEditStage')||{}).value||'dev'), label:((document.getElementById('deviceEditLabel')||{}).value||'').trim(), notes:((document.getElementById('deviceEditNotes')||{}).value||'').trim() };
    if(!payload.device_id){ alert('设备 ID 不能为空'); return; }
    fetch('/api/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/test-devices',{method:'POST',headers:{'Content-Type':'application/json'},credentials:'same-origin',body:JSON.stringify(payload)}).then(function(r){return r.json();}).then(function(d){ if(d.error){alert(d.error);return;} resetDeviceForm(); loadTestDevices(); });
}
function deleteTestDevice(id){ if(!id||!confirm('确定删除该设备？')) return; fetch('/api/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/test-devices/'+encodeURIComponent(id),{method:'DELETE',credentials:'same-origin'}).then(function(r){return r.json();}).then(function(d){ if(d.error){alert(d.error);return;} loadTestDevices(); }); }
function openVersionModal(preselectedChannel, preselectedStage){ document.getElementById('versionModalTitle').textContent='新建版本'; document.getElementById('versionEditId').value=''; document.getElementById('chkCommercialMode').checked=false; toggleCommercialMode(); var defCh = preselectedChannel || ((PROJECT_CHANNELS&&PROJECT_CHANNELS[0]) ? PROJECT_CHANNELS[0].id : 'dev'); var defSt = preselectedStage || 'dev'; ['versionChannel','versionStage','versionPlatform','versionName','versionStatus','versionApkPath','versionResourcePath','versionConfigPath','versionJenkinsJob','versionChangelog','versionNotes','versionPackageName','versionMinSdk','versionBundleId','versionMinIosVersion'].forEach(function(id){ var e=document.getElementById(id); if(e) e.value=e.type==='textarea' ? '' : (id==='versionChannel' ? defCh : (id==='versionStage' ? defSt : (id==='versionPlatform' ? 'android' : (id==='versionStatus' ? 'active' : '')))); }); var distributionEl=document.getElementById('versionDistributionMethod'); if(distributionEl) distributionEl.value='direct'; var rec=document.getElementById('versionChangelogRecommended'); if(rec) rec.checked=false; var hintRow=document.getElementById('versionCodeHintRow'); if(hintRow) hintRow.classList.add('hidden'); syncVersionPlatformFields(); suggestVersionApkPath(); syncDerivedVersionPaths(); switchVersionModalTab('identity'); document.getElementById('versionModal').classList.remove('hidden'); ensureUnityVersionSelect(''); }
function closeVersionModal(){ document.getElementById('versionModal').classList.add('hidden'); }
function getActiveStageId(){
    var stageBtn=document.querySelector('.channel-stage-tab.bg-white');
    return (stageBtn&&stageBtn.getAttribute('data-stage'))||'dev';
}
function versionCodesInGroup(versionName){
    var vn=(versionName||'').trim();
    return allVersions.filter(function(x){ return (x.version_name||'').trim()===vn; });
}
function versionCodesInGroupForContext(versionName){
    var vn=(versionName||'').trim();
    var cid=String(window._activeChannelId||'').toLowerCase();
    var sid=getActiveStageId();
    return versionCodesInGroup(vn).filter(function(v){
        return String(v.channel||'').toLowerCase()===cid && (v.stage||'dev')===sid;
    });
}
function pickVersionGroupTemplate(versionName){
    var inCtx=versionCodesInGroupForContext(versionName);
    if(inCtx.length) return inCtx[0];
    var cid=String(window._activeChannelId||'').toLowerCase();
    var anyChannel=versionCodesInGroup(versionName).filter(function(v){
        return String(v.channel||'').toLowerCase()===cid;
    });
    if(anyChannel.length) return anyChannel[0];
    var all=versionCodesInGroup(versionName);
    return all.length?all[0]:null;
}
function enrichVersionRow(v){
    v.stage=v.stage||'dev';
    var st=(VERSION_STAGES||[]).find(function(s){ return (s.id||'')===v.stage; });
    v.stage_label=v.stage_label||(st&&st.name)||v.stage;
    var ch=(PROJECT_CHANNELS||[]).find(function(c){ return String(c.id||'')===String(v.channel||''); });
    if(!ch&&CHANNELS_FULL&&CHANNELS_FULL[v.channel]) ch={id:v.channel,name:CHANNELS_FULL[v.channel].name||v.channel};
    v.channel_label=v.channel_label||(ch&&ch.name)||v.channel;
    return v;
}
function reloadProjectVersions(){
    return fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/list', {credentials:'same-origin'})
        .then(function(r){ return r.json(); })
        .then(function(d){
            if(!d||!d.versions) return;
            allVersions=(d.versions||[]).map(enrichVersionRow);
        });
}
function hasDuplicateVersionCode(versionName, versionCode, excludeId){
    var vc=String(versionCode||'').trim();
    if(!vc) return false;
    return versionCodesInGroup(versionName).some(function(x){
        if(excludeId&&(x.id||'')===excludeId) return false;
        return String(x.version_code||'').trim()===vc;
    });
}
function suggestNextVersionCode(versionName){
    var maxN=0;
    versionCodesInGroupForContext(versionName).forEach(function(x){
        var n=parseInt(String(x.version_code||'').trim(),10);
        if(!isNaN(n)&&n>maxN) maxN=n;
    });
    return String(maxN+1);
}
function openVersionCodeModal(id){
    var v=allVersions.find(function(x){ return (x.id||'')===id; });
    if(!v) return;
    var codeEl=document.getElementById('versionCodeEditValue');
    var statusEl=document.getElementById('versionCodeEditStatus');
    var changeEl=document.getElementById('versionCodeEditChangelog');
    document.getElementById('versionCodeEditId').value=v.id||'';
    document.getElementById('versionCodeEditMode').value='edit';
    document.getElementById('versionCodeCloneFromId').value='';
    var titleEl=document.getElementById('versionCodeModalTitle');
    if(titleEl) titleEl.textContent='编辑 VersionCode';
    document.getElementById('versionCodeEditVersionName').textContent='Version: '+(v.version_name||'-');
    if(codeEl) codeEl.value=v.version_code||'';
    if(statusEl) statusEl.value=normalizeVersionStatus(v.version_status||'active');
    if(changeEl) changeEl.value=v.changelog_text||'';
    setVersionCodeRuntimeCompatFormFields(v);
    document.getElementById('versionCodeModal').classList.remove('hidden');
}
function openAddVersionCodeModal(versionName){
    var template=pickVersionGroupTemplate(versionName);
    if(!template){ alert('未找到该版本组，请先在当前渠道/阶段创建至少一个版本'); return; }
    var stageLabel=template.stage_label||template.stage||'dev';
    var chLabel=template.channel_label||template.channel||'';
    document.getElementById('versionCodeEditId').value='';
    document.getElementById('versionCodeEditMode').value='add';
    document.getElementById('versionCodeCloneFromId').value=template.id||'';
    var titleEl=document.getElementById('versionCodeModalTitle');
    if(titleEl) titleEl.textContent='新增 VersionCode';
    document.getElementById('versionCodeEditVersionName').textContent='Version: '+(versionName||'-')+' · 将添加到「'+chLabel+' / '+stageLabel+'」';
    var codeEl=document.getElementById('versionCodeEditValue');
    var statusEl=document.getElementById('versionCodeEditStatus');
    var changeEl=document.getElementById('versionCodeEditChangelog');
    if(codeEl) codeEl.value=suggestNextVersionCode(versionName);
    if(statusEl) statusEl.value='active';
    if(changeEl) changeEl.value='';
    setVersionCodeRuntimeCompatFormFields(template||{});
    document.getElementById('versionCodeModal').classList.remove('hidden');
}
function closeVersionCodeModal(){ document.getElementById('versionCodeModal').classList.add('hidden'); }
function saveVersionCodeModal(){
    var mode=((document.getElementById('versionCodeEditMode')||{}).value||'edit').trim();
    var versionCode=((document.getElementById('versionCodeEditValue')||{}).value||'').trim();
    if(!versionCode){ alert('Version Code 不能为空'); return; }
    var versionStatus=normalizeVersionStatus(((document.getElementById('versionCodeEditStatus')||{}).value||'active'));
    var changelog=((document.getElementById('versionCodeEditChangelog')||{}).value||'').trim();
    if(mode==='add'){
        var cloneId=((document.getElementById('versionCodeCloneFromId')||{}).value||'').trim();
        var template=allVersions.find(function(x){ return (x.id||'')===cloneId; });
        if(!template){ alert('模板版本不存在'); return; }
        var vn=(template.version_name||'').trim();
        if(hasDuplicateVersionCode(vn, versionCode, '')){
            alert('版本 '+vn+' 下已存在 Version Code「'+versionCode+'」，请修改后再保存');
            return;
        }
        var payload={
            channel:template.channel||'',
            stage:template.stage||'dev',
            platform:template.platform||'android',
            version_status:versionStatus,
            version_name:vn,
            version_mode:template.version_mode||'general',
            version_code:versionCode,
            distribution_method:template.distribution_method||'',
            package_name:template.package_name||'',
            min_sdk:template.min_sdk||'',
            bundle_id:template.bundle_id||'',
            min_ios_version:template.min_ios_version||'',
            apk_path:template.apk_path||'',
            resource_path:template.resource_path||'',
            config_path:template.config_path||'',
            jenkins_job_id:template.jenkins_job_id||'',
            changelog:changelog,
            changelog_recommended:false,
            notes:template.notes||''
        };
        Object.assign(payload, readVersionCodeRuntimeCompatPayload(vn));
        if((template.version_mode||'general')==='commercial'&&template.pipeline){
            try{ payload.pipeline=JSON.parse(JSON.stringify(template.pipeline)); }catch(e){ payload.pipeline=template.pipeline; }
        }
        fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/create', {
            method:'POST',
            headers:{ 'Content-Type':'application/json' },
            body:JSON.stringify(payload),
            credentials:'same-origin'
        }).then(function(r){ return r.json(); }).then(function(d){
            if(d.error){ alert(d.error); return; }
            reloadProjectVersions().then(function(){
                closeVersionCodeModal();
                renderChannelsView();
            });
        });
        return;
    }
    var id=(document.getElementById('versionCodeEditId')||{}).value||'';
    var v=allVersions.find(function(x){ return (x.id||'')===id; });
    if(!v){ alert('版本不存在'); return; }
    var vn=(v.version_name||'').trim();
    if(hasDuplicateVersionCode(vn, versionCode, id)){
        alert('版本 '+vn+' 下已存在 Version Code「'+versionCode+'」，无法保存');
        return;
    }
    var payload={
        id:v.id||'',
        channel:v.channel||'',
        stage:v.stage||'dev',
        platform:v.platform||'android',
        version_status:versionStatus,
        version_name:vn,
        version_mode:v.version_mode||'general',
        version_code:versionCode,
        distribution_method:v.distribution_method||'',
        package_name:v.package_name||'',
        min_sdk:v.min_sdk||'',
        bundle_id:v.bundle_id||'',
        min_ios_version:v.min_ios_version||'',
        apk_path:v.apk_path||'',
        resource_path:v.resource_path||'',
        config_path:v.config_path||'',
        jenkins_job_id:v.jenkins_job_id||'',
        changelog:changelog,
        changelog_recommended:!!v.changelog_recommended,
        notes:v.notes||''
    };
    Object.assign(payload, readVersionCodeRuntimeCompatPayload(vn));
    payload.edit_scope='version_code';
    if((v.version_mode||'general')==='commercial'){ payload.pipeline=v.pipeline||{}; }
    fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/update', {
        method:'POST',
        headers:{ 'Content-Type':'application/json' },
        body:JSON.stringify(payload),
        credentials:'same-origin'
    }).then(function(r){ return r.json(); }).then(function(d){
        if(d.error){ alert(d.error); return; }
        reloadProjectVersions().then(function(){
            closeVersionCodeModal();
            renderChannelsView();
        });
    });
}

function editVersion(id){ var v=allVersions.find(function(x){ return (x.id||'')===id; }); if(!v) return; document.getElementById('versionModalTitle').textContent='编辑版本'; document.getElementById('versionEditId').value=v.id||''; var vm = v.version_mode || 'general'; document.getElementById('chkCommercialMode').checked = (vm==='commercial'); toggleCommercialMode(); document.getElementById('versionChannel').value=v.channel||'dev'; var stageEl=document.getElementById('versionStage'); if(stageEl) stageEl.value=v.stage||'dev'; var platformEl=document.getElementById('versionPlatform'); if(platformEl) platformEl.value=v.platform||'android'; var statusEl=document.getElementById('versionStatus'); if(statusEl) statusEl.value=normalizeVersionStatus(v.version_status||'active'); document.getElementById('versionName').value=v.version_name||''; document.getElementById('versionApkPath').value=v.apk_path||''; document.getElementById('versionResourcePath').value=v.resource_path||''; document.getElementById('versionConfigPath').value=v.config_path||''; document.getElementById('versionJenkinsJob').value=v.jenkins_job_id||''; document.getElementById('versionChangelog').value=v.changelog_text||''; document.getElementById('versionChangelogRecommended').checked=!!v.changelog_recommended; document.getElementById('versionNotes').value=v.notes||''; var distributionEl=document.getElementById('versionDistributionMethod'); if(distributionEl) distributionEl.value=v.distribution_method||''; var packageNameEl=document.getElementById('versionPackageName'); if(packageNameEl) packageNameEl.value=v.package_name||''; var minSdkEl=document.getElementById('versionMinSdk'); if(minSdkEl) minSdkEl.value=v.min_sdk||''; var bundleIdEl=document.getElementById('versionBundleId'); if(bundleIdEl) bundleIdEl.value=v.bundle_id||''; var minIosEl=document.getElementById('versionMinIosVersion'); if(minIosEl) minIosEl.value=v.min_ios_version||''; var hintRow=document.getElementById('versionCodeHintRow'); var codeDisplay=document.getElementById('versionCodeDisplay'); if(hintRow){ if(v.version_code){ hintRow.classList.remove('hidden'); if(codeDisplay) codeDisplay.textContent=String(v.version_code); } else { hintRow.classList.add('hidden'); } } // 商业级参数回填
    var pipeline=v.pipeline||{}; if(pipeline) restorePipeline(pipeline);
    var savedUnity=(pipeline.apk_build&&pipeline.apk_build.unity_version)||'';
    syncVersionPlatformFields(); suggestVersionApkPath(); syncDerivedVersionPaths(v.version_code||''); switchVersionModalTab('identity'); document.getElementById('versionModal').classList.remove('hidden'); ensureUnityVersionSelect(savedUnity); }

function deleteVersion(id){ if(!requireDeleteConfirm('VersionCode: '+id)) return; fetch('/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/delete/'+encodeURIComponent(id), { method: 'DELETE', credentials: 'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } allVersions = allVersions.filter(function(x){ return (x.id||'')!==id; }); renderChannelsView(); }); }

function saveVersion(){ var id=document.getElementById('versionEditId').value; var current=id?allVersions.find(function(x){ return (x.id||'')===id; }):null; var ch=document.getElementById('versionChannel').value; var stageEl=document.getElementById('versionStage'); var stageVal=stageEl?stageEl.value:'dev'; var platform=document.getElementById('versionPlatform').value||'android'; var versionStatus=normalizeVersionStatus((document.getElementById('versionStatus')||{}).value||'active'); var vn=document.getElementById('versionName').value.trim()||'1.0.0'; var apkPath=document.getElementById('versionApkPath').value.trim(); if(!apkPath){ var info=CHANNELS_FULL&&CHANNELS_FULL[ch]; var sd=STAGE_DIR_MAP[stageVal]||'dev'; var ext=platform==='ios'?'.ipa':'.apk'; var an=PROJECT_ID+'_'+vn.replace(new RegExp("\\\\s","g"),"")+ext; apkPath=(info&&info.apk_subdir)?(info.apk_subdir+'/'+sd+'/'+an):(sd+'/'+an); } var fixedVersionCode=(current&&current.version_code)?String(current.version_code).trim():''; syncDerivedVersionPaths(fixedVersionCode); var payload={ channel: ch, stage: stageVal, platform: platform, version_status: versionStatus, version_name: vn, version_mode: _versionMode, version_code: fixedVersionCode, distribution_method: (document.getElementById('versionDistributionMethod')||{}).value||'', package_name: (document.getElementById('versionPackageName')||{}).value||'', min_sdk: (document.getElementById('versionMinSdk')||{}).value||'', bundle_id: (document.getElementById('versionBundleId')||{}).value||'', min_ios_version: (document.getElementById('versionMinIosVersion')||{}).value||'', apk_path: apkPath, resource_path: document.getElementById('versionResourcePath').value.trim(), config_path: document.getElementById('versionConfigPath').value.trim(), jenkins_job_id: document.getElementById('versionJenkinsJob').value.trim(), changelog: document.getElementById('versionChangelog').value.trim(), changelog_recommended: !!document.getElementById('versionChangelogRecommended').checked, notes: document.getElementById('versionNotes').value.trim(), edit_scope:'version_group' }; if(_versionMode==='commercial'){ payload.pipeline=collectPipeline(); var err=validateCommercialPipeline(payload.pipeline); if(err){ alert(err); return; } } var url='/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/create'; var method='POST'; if(id){ payload.id=id; url='/admin/projects/'+encodeURIComponent(PROJECT_ID)+'/versions/update'; } fetch(url, { method: method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(payload), credentials: 'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ if(d.error){ alert(d.error); return; } if(d.version){ var chOpt=document.getElementById('versionChannel'); d.version.channel_label=chOpt&&chOpt.options[chOpt.selectedIndex]?chOpt.options[chOpt.selectedIndex].text:d.version.channel; d.version.stage=stageVal; d.version.stage_label=(stageEl&&stageEl.options[stageEl.selectedIndex]?stageEl.options[stageEl.selectedIndex].text:'开发'); d.version.platform=platform; d.version.platform_label=platform==='ios'?'iOS':'Android'; d.version.version_status=versionStatus; d.version.version_mode=_versionMode; d.version.commercial_release=payload.commercial_release||null; d.version.distribution_method=payload.distribution_method || (platform==='ios'?'testflight':'direct'); d.version.package_name=payload.package_name; d.version.min_sdk=payload.min_sdk; d.version.bundle_id=payload.bundle_id; d.version.min_ios_version=payload.min_ios_version; d.version.changelog_text=payload.changelog; d.version.changelog_recommended=payload.changelog_recommended; var idx=allVersions.findIndex(function(x){ return (x.id||'')===(d.version.id||''); }); if(idx>=0) allVersions[idx]=d.version; else allVersions.push(d.version); } closeVersionModal(); renderChannelsView(); }); }

renderChannelsView();
refreshVersionBuildState();
ensureVersionBuildStateTimer();
syncVersionPlatformFields();
fetchUnityVersionCatalog(function(){ renderUnityVersionSelect(''); });
