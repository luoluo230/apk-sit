
    var PROJECT_ID = "{{ project_id or '' }}";
    var VERSION_ID = "{{ version_id or '' }}";
    var CHANNEL_ID = "{{ channel_id or '' }}";
    var STAGE_ID = "{{ stage_id or '' }}";
    var VERSION_MODE = "{{ version_mode or 'general' }}";
    var PREFERRED_INSTANCE_ID = "{{ preferred_instance_id or '' }}";
    var VERSION_LOCK_PARAMS = {{ 'true' if version_lock_params else 'false' }};
    var CANONICAL_VERSION_NAME = {{ (canonical_version_name|default('')|tojson) }};
    var CANONICAL_VERSION_CODE = {{ (canonical_version_code|default('')|tojson) }};
    var CANONICAL_GIT_BRANCH = {{ (default_git_branch|default('')|tojson) }};
    var VERSION_PIPELINE = {{ (version_pipeline or {})|tojson }};
    var VERSION_INFO = {{ (version_info or {})|tojson }};
    var INSTANCE_META = {};
    function modeLabel(v){ return normalizedType(v)==='commercial' ? '商业级' : '通用级'; }
    function normalizedType(v){
        var t=String(v||'general').trim().toLowerCase();
        if(t!=='commercial') t='general';
        return t;
    }
    function getCsrfToken(){
        var m=document.querySelector('meta[name="csrf-token"]');
        return m ? (m.getAttribute('content')||'') : '';
    }
    function versionGitBranch(){ return (document.getElementById('GIT_BRANCH')||{}).value || ''; }
    function _buildStorageKey(suffix){ return 'buildwf:'+PROJECT_ID+':'+VERSION_ID+':'+suffix; }
    function persistInstanceChoice(){ try{ localStorage.setItem(_buildStorageKey('instance_id'), selectedInstanceId()||''); }catch(e){} }
    function loadInstanceChoice(){ try{ return localStorage.getItem(_buildStorageKey('instance_id'))||''; }catch(e){ return ''; } }
    function saveActiveBuild(instanceId, buildNumber){ try{ localStorage.setItem(_buildStorageKey('active_build'), JSON.stringify({instance_id:instanceId||'', build_number:buildNumber||''})); }catch(e){} }
    function loadActiveBuild(){ try{ var s=localStorage.getItem(_buildStorageKey('active_build')); return s?JSON.parse(s):null; }catch(e){ return null; } }
    function clearActiveBuild(){ try{ localStorage.removeItem(_buildStorageKey('active_build')); }catch(e){} }
    function bindPanelState(panelId, storageKey, defaultCollapsed){
        var panel=document.getElementById(panelId);
        if(!panel) return;
        var body=panel.querySelector('[data-panel-body]');
        var toggle=document.getElementById('commercialParamsToggle');
        var chevron=document.getElementById('commercialParamsChevron');
        var collapsed=false;
        try{ collapsed=localStorage.getItem(storageKey)==='1'; }catch(e){}
        if(defaultCollapsed && localStorage.getItem(storageKey)===null) collapsed=true;
        function applyState(){
            if(!body) return;
            body.style.display=collapsed?'none':'block';
            if(chevron) chevron.style.transform=collapsed?'rotate(-90deg)':'';
        }
        applyState();
        if(toggle){
            toggle.onclick=function(){
                collapsed=!collapsed;
                try{ localStorage.setItem(storageKey, collapsed?'1':'0'); }catch(e){}
                applyState();
            };
        }
    }
    window._cpLang = window._cpLang || 'zh';
    function _escHtml(s){ return String(s==null?'':s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;'); }
    function _onOff(v){
        if(window._cpLang==='en'){
            return v ? '<span class="text-emerald-600 font-medium">Enabled</span>' : '<span class="text-slate-400">Disabled</span>';
        }
        return v ? '<span class="text-emerald-600 font-medium">启用</span>' : '<span class="text-slate-400">禁用</span>';
    }
    function _cpLabel(k){
        var map={
            APP_NAME:{zh:'应用名',en:'App Name'},
            VERSION_NAME:{zh:'版本名',en:'Version Name'},
            VERSION_CODE:{zh:'版本号',en:'Version Code'},
            UNITY_VERSION:{zh:'Unity 版本',en:'Unity Version'},
            OUTPUT_BASE_DIR:{zh:'输出目录',en:'Output Base Dir'},
            GIT_BRANCH:{zh:'Git 分支',en:'Git Branch'},
            RELEASE_ENVIRONMENT:{zh:'发布环境',en:'Release Environment'},
            RELEASE_CHANNEL:{zh:'发布渠道',en:'Release Channel'},
            RELEASE_PLATFORM:{zh:'发布平台',en:'Release Platform'},
            RELEASE_MODE:{zh:'发布模式',en:'Release Mode'},
            RELEASE_TARGETS:{zh:'发布对象',en:'Release Targets'},
            RELEASE_UPLOAD_MODE:{zh:'上传模式',en:'Upload Mode'},
            CONFIG_REMOTE_PREFIX:{zh:'配置远端前缀',en:'Config Remote Prefix'},
            RESOURCE_PROVIDER:{zh:'资源引擎',en:'Resource Provider'},
            RESOURCE_SCENARIO:{zh:'资源场景',en:'Resource Scenario'},
            CODE_UNITS:{zh:'代码单元',en:'Code Units'},
            RESOURCE_UNITS:{zh:'资源单元',en:'Resource Units'}
        };
        var n=map[k]||{zh:k,en:k};
        return window._cpLang==='en' ? (n.en+' / '+k) : (n.zh+' / '+k);
    }
    function _inputVal(id){
        var el=document.getElementById(id);
        return (el && el.value!=null) ? String(el.value).trim() : '';
    }
    function renderCommercialSummary(){
        var panel=document.getElementById('commercialParamsPanel');
        var body=document.getElementById('commercialParamsBody');
        if(!panel||!body) return;
        if(normalizedType(VERSION_MODE)!=='commercial'){
            panel.classList.add('hidden');
            return;
        }
        panel.classList.remove('hidden');
        var pp=VERSION_PIPELINE||{};
        var rows=[];
        var ce=pp.config_export||{};
        var rb=pp.resource_build||{};
        var hr=pp.hot_release||{};
        var ab=pp.apk_build||{};
        var isEn=(window._cpLang==='en');
        rows.push('<div class="grid grid-cols-1 md:grid-cols-2 gap-2">');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step1 '+(isEn?'Config Export':'配置导出')+'</div><div class="text-xs text-slate-600">'+_onOff(ce.enabled)+' · '+(isEn?'Env':'环境')+': '+_escHtml(ce.environment||'-')+' · '+(isEn?'Platform':'平台')+': '+_escHtml(ce.platform||'-')+' · '+(isEn?'Version':'版本')+': '+_escHtml(ce.client_version||CANONICAL_VERSION_NAME||'-')+'</div><div class="text-xs text-slate-600 mt-1">OSS Prefix: '+_escHtml(ce.remote_prefix||'-')+(ce.include_code?(isEn?' · Include code':' · 含代码'):'')+'</div></div>');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step2 '+(isEn?'Resource Build':'资源打包')+'</div><div class="text-xs text-slate-600">'+_onOff(rb.enabled)+' · '+(isEn?'Provider':'引擎')+': '+_escHtml(rb.provider||'-')+' · '+(isEn?'Scenario':'场景')+': '+_escHtml(rb.scenario||'-')+'</div></div>');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step3 '+(isEn?'Hot Release':'热更发布')+'</div><div class="text-xs text-slate-600">'+_onOff(hr.enabled)+' · '+(isEn?'Targets':'对象')+': '+_escHtml(hr.release_targets||'-')+' · '+(isEn?'Mode':'模式')+': '+_escHtml(hr.release_mode||'-')+' · '+(isEn?'Upload':'上传')+': '+_escHtml(hr.release_upload_mode||'-')+'</div>');
        if(hr.release_hot_labels) rows.push('<div class="pl-2 text-xs text-slate-600">热更标签: '+_escHtml(hr.release_hot_labels)+'</div>');
        if(hr.code_enabled) rows.push('<div class="pl-2 text-xs text-slate-600"><span class="text-blue-600">代码包</span> 压缩 '+_escHtml(hr.code_compression||'-')+' · 加密 '+_escHtml(hr.code_encryption||'-')+' · 签名 '+_escHtml(hr.code_signature||'-')+'</div>');
        if(hr.resource_enabled) rows.push('<div class="pl-2 text-xs text-slate-600"><span class="text-emerald-600">资源包</span> 压缩 '+_escHtml(hr.resource_compression||'-')+' · 加密 '+_escHtml(hr.resource_encryption||'-')+' · 签名 '+_escHtml(hr.resource_signature||'-')+'</div>');
        rows.push('</div>');
        rows.push('<div class="rounded-lg border border-violet-100 bg-white p-2"><div class="text-xs font-semibold text-violet-700 mb-1">Step4 APK '+(isEn?'(Optional)':'（可选）')+'</div><div class="text-xs text-slate-600">'+_onOff(ab.enabled)+' · Unity '+_escHtml(ab.unity_version||'-')+' · '+(isEn?'Branch':'分支')+' '+_escHtml(ab.git_branch||CANONICAL_GIT_BRANCH||'-')+'</div></div>');
        rows.push('</div>');
        var missing=[];
        if(!_inputVal('APP_NAME')) missing.push('APP_NAME');
        if(!_inputVal('VERSION_NAME')) missing.push('VERSION_NAME');
        if(!_inputVal('VERSION_CODE')) missing.push('VERSION_CODE');
        if(!_inputVal('UNITY_VERSION') && !String(ab.unity_version||'').trim()) missing.push('UNITY_VERSION');
        if(!_inputVal('OUTPUT_BASE_DIR') && !String(ab.output_base_dir||'').trim()) missing.push('OUTPUT_BASE_DIR');
        if(!_inputVal('GIT_BRANCH') && !String(ab.git_branch||'').trim()) missing.push('GIT_BRANCH');
        if(!String(ce.remote_prefix||'').trim()) missing.push('CONFIG_REMOTE_PREFIX');
        if(!String(hr.release_targets||'').trim()) missing.push('RELEASE_TARGETS');
        if(missing.length){
            rows.push('<div class="mt-2 rounded border border-amber-200 bg-amber-50 px-2 py-1 text-[11px] text-amber-700">参数缺失预警：'+_escHtml(missing.join(', '))+'（建议先回版本编辑页补齐流水线配置）</div>');
        }
        var coverage=[
            ['APP_NAME', _inputVal('APP_NAME') || ab.app_name],
            ['VERSION_NAME', _inputVal('VERSION_NAME') || CANONICAL_VERSION_NAME],
            ['VERSION_CODE', _inputVal('VERSION_CODE') || CANONICAL_VERSION_CODE],
            ['UNITY_VERSION', _inputVal('UNITY_VERSION') || ab.unity_version],
            ['OUTPUT_BASE_DIR', _inputVal('OUTPUT_BASE_DIR') || ab.output_base_dir],
            ['GIT_BRANCH', _inputVal('GIT_BRANCH') || ab.git_branch || CANONICAL_GIT_BRANCH],
            ['RELEASE_ENVIRONMENT', hr.release_environment || ce.environment],
            ['RELEASE_CHANNEL', hr.release_channel || _inputVal('CHANNEL')],
            ['RELEASE_PLATFORM', ce.platform || (VERSION_INFO.platform||'')],
            ['RELEASE_MODE', hr.release_mode],
            ['RELEASE_TARGETS', hr.release_targets],
            ['RELEASE_UPLOAD_MODE', hr.release_upload_mode],
            ['CONFIG_REMOTE_PREFIX', ce.remote_prefix],
            ['RESOURCE_PROVIDER', rb.provider],
            ['RESOURCE_SCENARIO', rb.scenario],
            ['CODE_UNITS', hr.code_units],
            ['RESOURCE_UNITS', hr.resource_units]
        ];
        rows.push('<details class="mt-2 rounded border border-violet-200 bg-white" open><summary class="cursor-pointer select-none px-2 py-1 text-xs font-semibold text-violet-700">'+(isEn?'Parameter Coverage (Commercial)':'参数覆盖检查（商业级）')+'</summary>');
        rows.push('<div class="rounded border-t border-violet-100 overflow-hidden"><table class="w-full text-[11px]"><thead class="bg-slate-50"><tr><th class="text-left px-2 py-1 text-slate-500">'+(isEn?'Parameter':'参数')+'</th><th class="text-left px-2 py-1 text-slate-500">'+(isEn?'Status':'状态')+'</th><th class="text-left px-2 py-1 text-slate-500">'+(isEn?'Current Value':'当前值')+'</th></tr></thead><tbody>'+
            coverage.map(function(item){
                var ok=!!String(item[1]||'').trim();
                return '<tr class="border-t border-slate-100"><td class="px-2 py-1 text-slate-700">'+_escHtml(_cpLabel(item[0]))+'</td><td class="px-2 py-1">'+(ok?'<span class="text-emerald-600">'+(isEn?'OK':'已覆盖')+'</span>':'<span class="text-rose-600">'+(isEn?'Missing':'缺失')+'</span>')+'</td><td class="px-2 py-1 text-slate-600">'+_escHtml(String(item[1]||'-'))+'</td></tr>';
            }).join('')+
            '</tbody></table></div></details>');
        if(!ce.enabled && !rb.enabled && !hr.enabled && !ab.enabled){
            body.innerHTML='<p class="text-xs text-amber-700">未配置商业流水线步骤。请返回项目「版本管理」编辑该版本的商业级流水线后刷新本页。</p>';
        } else {
            body.innerHTML=rows.join('');
        }
    }
    function applyVersionCanonicalFields(){
        if(CANONICAL_VERSION_NAME){
            var vn=document.getElementById('VERSION_NAME');
            if(vn) vn.value=CANONICAL_VERSION_NAME;
        }
        if(CANONICAL_VERSION_CODE){
            var vc=document.getElementById('VERSION_CODE');
            if(vc) vc.value=String(CANONICAL_VERSION_CODE);
        }
        if(CANONICAL_GIT_BRANCH){
            var gb=document.getElementById('GIT_BRANCH');
            if(gb) gb.value=CANONICAL_GIT_BRANCH;
        }
    }
    function buildCommercialPlanFromVersion(){
        var plan={
            unityProjectPath:'',
            gitBranch: versionGitBranch(),
            appName: _inputVal('APP_NAME'),
            releaseVersion: _inputVal('VERSION_NAME'),
            versionCode: _inputVal('VERSION_CODE'),
            unityVersion: _inputVal('UNITY_VERSION'),
            outputBaseDir: _inputVal('OUTPUT_BASE_DIR'),
            releaseUpload: true,
            releaseActivate: false
        };
        if(CANONICAL_VERSION_NAME){ plan.releaseVersion=CANONICAL_VERSION_NAME; }
        if(CANONICAL_VERSION_CODE){ plan.versionCode=String(CANONICAL_VERSION_CODE); }
        var ch=document.getElementById('CHANNEL');
        if(ch&&ch.value){ plan.releaseChannel=ch.value; }
        var pp=VERSION_PIPELINE||{};
        var ce=pp.config_export||{};
        var rb=pp.resource_build||{};
        var hr=pp.hot_release||{};
        var ab=pp.apk_build||{};
        if(ce.enabled!=null) plan.configEnabled=!!ce.enabled;
        if(ce.remote_prefix) plan.configRemotePrefix=ce.remote_prefix;
        if(ce.include_code!=null) plan.configIncludeCode=!!ce.include_code;
        if(rb.enabled!=null) plan.resourceEnabled=!!rb.enabled;
        if(rb.provider) plan.resourceProvider=rb.provider;
        if(rb.scenario) plan.resourceScenario=rb.scenario;
        if(hr.enabled!=null) plan.hotReleaseEnabled=!!hr.enabled;
        if(hr.release_mode) plan.releaseMode=hr.release_mode;
        if(hr.release_environment) plan.releaseEnvironment=hr.release_environment;
        if(hr.release_channel) plan.releaseChannel=hr.release_channel;
        if(hr.release_targets) plan.releaseTargets=hr.release_targets;
        if(hr.release_hot_labels) plan.releaseHotLabels=hr.release_hot_labels;
        if(hr.release_upload_mode) plan.releaseUploadMode=hr.release_upload_mode;
        if(hr.release_rollback_target) plan.releaseRollbackTarget=hr.release_rollback_target;
        if(hr.release_compression_override) plan.releaseCompressionOverride=hr.release_compression_override;
        if(hr.release_encryption_override) plan.releaseEncryptionOverride=hr.release_encryption_override;
        if(hr.release_signature_override) plan.releaseSignatureOverride=hr.release_signature_override;
        if(hr.code_enabled!=null) plan.codeEnabled=!!hr.code_enabled;
        if(hr.code_compression) plan.codeCompression=hr.code_compression;
        if(hr.code_encryption) plan.codeEncryption=hr.code_encryption;
        if(hr.code_signature) plan.codeSignature=hr.code_signature;
        if(hr.code_units) plan.codeUnits=hr.code_units;
        if(hr.resource_enabled!=null) plan.resourceEnabled=!!hr.resource_enabled;
        if(hr.resource_compression) plan.resourceCompression=hr.resource_compression;
        if(hr.resource_encryption) plan.resourceEncryption=hr.resource_encryption;
        if(hr.resource_signature) plan.resourceSignature=hr.resource_signature;
        if(hr.resource_units) plan.resourceUnits=hr.resource_units;
        if(ab.app_name) plan.appName=ab.app_name;
        if(ab.unity_version) plan.unityVersion=ab.unity_version;
        if(ab.output_base_dir) plan.outputBaseDir=ab.output_base_dir;
        if(ab.unity_project_path) plan.unityProjectPath=ab.unity_project_path;
        var plat=(VERSION_INFO.platform||'android').toString();
        plan.releasePlatform=plat.charAt(0).toUpperCase()+plat.slice(1).toLowerCase();
        if(ce.platform) plan.releasePlatform=ce.platform;
        if(!plan.releaseVersion) plan.releaseVersion=CANONICAL_VERSION_NAME||'0.0.1';
        if(!plan.versionCode) plan.versionCode=String(CANONICAL_VERSION_CODE||'');
        if(!plan.releaseChannel && ch && ch.value) plan.releaseChannel=ch.value;
        return plan;
    }
    function ensureInstanceOption(instanceId){
        var sel=document.getElementById('jenkinsInstance');
        if(!sel||!instanceId) return Promise.resolve(false);
        for(var i=0;i<sel.options.length;i++){ if(sel.options[i].value===instanceId){ sel.value=instanceId; return Promise.resolve(true); } }
        return fetch('/api/jenkins-manage/instance?instance_id='+encodeURIComponent(instanceId), {credentials:'same-origin'})
            .then(function(r){ return r.json(); })
            .then(function(d){
                var inst=((d||{}).instance)||{};
                if(!inst.id) return false;
                INSTANCE_META[inst.id]={port:inst.port,task_name:(inst.task_name||'').trim()};
                var opt=document.createElement('option');
                opt.value=inst.id;
                opt.textContent=(inst.port||'') + ((inst.task_name&&inst.task_name.trim()) ? ' '+inst.task_name.trim() : '') + ' - ' + (inst.status==='running'?'运行中':'已停止');
                sel.appendChild(opt);
                sel.value=inst.id;
                return true;
            }).catch(function(){ return false; });
    }
    function selectedInstanceId(){ var s=document.getElementById('jenkinsInstance'); return (s&&s.value)||''; }
    function apiQuery(){ var id=selectedInstanceId(); return id ? '?instance_id='+encodeURIComponent(id) : ''; }
    function apiBody(obj){
        var id=selectedInstanceId();
        if(id) obj.instance_id=id;
        if(PROJECT_ID){ obj._project_id = PROJECT_ID; }
        if(VERSION_ID){ obj._version_id = VERSION_ID; }
        if(CHANNEL_ID){ obj._channel_id = CHANNEL_ID; }
        if(STAGE_ID){ obj._stage_id = STAGE_ID; }
        return obj;
    }
    function listAvailableUrl(){
        var q='instance_type='+encodeURIComponent(normalizedType(VERSION_MODE));
        if(PREFERRED_INSTANCE_ID){ q+='&include_instance_id='+encodeURIComponent(PREFERRED_INSTANCE_ID); }
        return '/api/jenkins-manage/list-available?'+q;
    }
    function loadJenkinsOptions(){
        return fetch(listAvailableUrl(), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var sel=document.getElementById('jenkinsInstance');
            if(!sel) return;
            while(sel.options.length>1) sel.remove(1);
            (d.instances||[]).forEach(function(i){
                INSTANCE_META[i.id]={port:i.port,task_name:(i.task_name||'').trim()};
                var opt=document.createElement('option');
                opt.value=i.id;
                var label=i.port + ((i.task_name&&i.task_name.trim()) ? ' '+i.task_name.trim() : '') + ' - ' + (i.status==='running'?'运行中':'已停止');
                opt.textContent=label;
                sel.appendChild(opt);
            });
            if(PREFERRED_INSTANCE_ID){
                for(var k=0;k<sel.options.length;k++){
                    if(sel.options[k].value===PREFERRED_INSTANCE_ID){ sel.value=PREFERRED_INSTANCE_ID; break; }
                }
            }
            if(!sel.value){
                var remembered=loadInstanceChoice();
                if(remembered){
                    for(var j=0;j<sel.options.length;j++){
                        if(sel.options[j].value===remembered){ sel.value=remembered; break; }
                    }
                }
            }
        });
    }
    function applyVersionLockParams(){
        if(!VERSION_LOCK_PARAMS) return;
        var lockIds=['APP_NAME','VERSION_NAME','VERSION_CODE','UNITY_VERSION','OUTPUT_BASE_DIR','CHANNEL','GIT_BRANCH'];
        lockIds.forEach(function(id){
            var el=document.getElementById(id);
            if(!el) return;
            if(el.tagName==='SELECT'){ el.disabled=true; }
            else { el.readOnly=true; }
            el.classList.add('bg-slate-100');
        });
    }
    function loadLastParams(){
        return fetch('/api/build/last-successful-params'+apiQuery(), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            if(d && typeof d==='object'){ for(var k in d){ var el=document.getElementById(k); if(el) el.value=d[k]||''; } }
        });
    }
    function setBuilding(yes){
        var startBtn=document.getElementById('btnTrigger');
        var stopBtn=document.getElementById('btnStop');
        var sel=document.getElementById('jenkinsInstance');
        if(yes){
            startBtn.classList.add('hidden');
            stopBtn.classList.remove('hidden');
            if(sel) sel.disabled=true;
        } else{
            startBtn.classList.remove('hidden');
            stopBtn.classList.add('hidden');
            startBtn.disabled=false;
            var t=document.getElementById('btnTriggerText');
            if(t) t.textContent='开始构建';
            if(sel) sel.disabled=false;
            updateJenkinsConsoleLink('', '');
        }
    }
    function updateJenkinsConsoleLink(instanceId, buildNum){
        var row=document.getElementById('jenkinsConsoleRow');
        var link=document.getElementById('jenkinsConsoleLink');
        if(!row||!link) return;
        var id=instanceId||selectedInstanceId();
        if(!id){ row.classList.add('hidden'); return; }
        var m=INSTANCE_META[id]||{};
        var port=m.port;
        if(!port){ row.classList.add('hidden'); return; }
        var url='http://127.0.0.1:'+port+'/job/Android/';
        if(buildNum){ url+=String(buildNum)+'/console'; }
        link.href=url;
        link.textContent=buildNum?('进入 Jenkins 控制台（#'+buildNum+'）'):'进入 Jenkins 控制台';
        row.classList.remove('hidden');
    }
    function statusClass(r){
        if(!r) return 'bg-gray-200 text-gray-700';
        r=r.toUpperCase();
        if(r==='SUCCESS') return 'bg-green-100 text-green-800';
        if(r==='FAILURE'||r==='ABORTED') return 'bg-red-100 text-red-800';
        if(r==='UNSTABLE') return 'bg-yellow-100 text-yellow-800';
        return 'bg-gray-100 text-gray-700';
    }
    function loadHistory(){
        if(!VERSION_ID){ document.getElementById('buildHistory').innerHTML='<li class="text-gray-500 text-sm">无法加载</li>'; return Promise.resolve(); }
        var q='version_id='+encodeURIComponent(VERSION_ID);
        return fetch('/api/build/history-by-version?'+q, {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
            var list=document.getElementById('buildHistory');
            if(!d.builds||!d.builds.length){ list.innerHTML='<li class="text-gray-500 text-sm">本版本暂无构建记录</li>'; return d; }
            list.innerHTML=d.builds.slice(0,12).map(function(b){
                var result=b.result||(b.building?'BUILDING':'');
                var badge='<span class="inline-block px-2 py-0.5 rounded text-xs font-medium '+statusClass(result)+'">'+result+'</span>';
                var iid=(b.instance_id||'').replace(/'/g,'');
                return '<li class="py-1.5 border-b border-gray-100 last:border-0"><a href="#" onclick="loadLog('+b.number+',\\\''+iid+'\\\');return false" class="text-blue-600 hover:underline font-medium">#'+b.number+'</a> '+badge+(iid?'<span class="text-[10px] text-gray-400 ml-1">'+iid.slice(0,8)+'</span>':'')+'</li>';
            }).join('');
            return d;
        });
    }
    function resolveEffectiveBuildNumber(triggeredBuildNumber){
        var triggeredNum = parseInt(triggeredBuildNumber, 10);
        if(!triggeredNum || triggeredNum<=0) return Promise.resolve(triggeredBuildNumber);
        if(!VERSION_ID) return Promise.resolve(triggeredNum);
        var q='version_id='+encodeURIComponent(VERSION_ID);
        return fetch('/api/build/history-by-version?'+q, {credentials:'same-origin'})
            .then(function(r){ return r.json(); })
            .then(function(d){
                var builds=(d&&d.builds)||[];
                if(!builds.length) return triggeredNum;
                var top=builds[0]||{};
                var topNum=parseInt(top.number,10)||0;
                var topBuilding=!!top.building || String(top.result||'').toUpperCase()==='BUILDING';
                // 触发后若 Jenkins 已产生更高编号（或最新正在构建），以最新编号为准
                if(topNum>triggeredNum || (topNum>=triggeredNum && topBuilding)){
                    return topNum;
                }
                return triggeredNum;
            })
            .catch(function(){ return triggeredNum; });
    }
    function loadLog(num, optInstanceId){
        var el=document.getElementById('buildLog');
        var instId=optInstanceId||selectedInstanceId();
        if(!instId){ el.textContent='请先选择 Jenkins 实例'; return; }
        el.textContent='加载中...';
        fetch('/api/build/log/'+num+'?instance_id='+encodeURIComponent(instId), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ el.textContent=t||'（无日志）'; el.scrollTop=el.scrollHeight; });
    }
    function pollLogAndStatus(buildNum, optInstanceId){
        var el=document.getElementById('buildLog');
        var instId=optInstanceId||selectedInstanceId();
        if(!buildNum||!instId) return;
        function logUrl(){ return '/api/build/log/'+buildNum+'?instance_id='+encodeURIComponent(instId); }
        function statusUrl(){ return '/api/build/'+buildNum+'/status?instance_id='+encodeURIComponent(instId); }
        function fetchLogOnce(cb){
            fetch(logUrl(), {credentials:'same-origin'}).then(r=>r.text()).then(function(t){
                el.textContent=t||'（无日志）';
                el.scrollTop=el.scrollHeight;
                if(cb) cb();
            }).catch(function(){ if(cb) cb(); });
        }
        function tick(){
            fetch(statusUrl(), {credentials:'same-origin'}).then(r=>r.json()).then(function(st){
                var status=(st&&st.status)||'';
                var done=st&&!st.building&&status!=='BUILDING'&&status!=='QUEUED';
                if(done){
                    stopPoll();
                    fetchLogOnce(function(){
                        setBuilding(false);
                        clearActiveBuild();
                        var stEl=document.getElementById('buildStatus');
                        if(stEl){
                            stEl.textContent='构建 #'+buildNum+' 已结束: '+status;
                            stEl.className='mt-3 text-sm min-h-[1.5rem] '+(status==='SUCCESS'?'text-green-600':'text-red-600');
                        }
                        loadHistory();
                    });
                    return;
                }
                fetchLogOnce();
            }).catch(function(){ fetchLogOnce(); });
        }
        tick();
        window._logTimer=setInterval(tick, 2500);
    }
    function stopPoll(){ if(window._logTimer){ clearInterval(window._logTimer); window._logTimer=null; } }
    function resumeVersionBuild(){
        var logEl=document.getElementById('buildLog');
        var active=loadActiveBuild();
        loadHistory().then(function(d){
            var builds=(d&&d.builds)||[];
            var target=null;
            if(active&&active.build_number){
                for(var i=0;i<builds.length;i++){ if(builds[i].number===active.build_number){ target=builds[i]; break; } }
                if(!target){ target={number:active.build_number,instance_id:active.instance_id,building:true,result:''}; }
            }
            if(!target&&builds.length) target=builds[0];
            if(!target||!target.number){
                if(logEl) logEl.textContent='点击左侧「本版本构建历史」中的某次构建可查看日志；开始构建后此处将自动刷新。';
                setBuilding(false);
                return;
            }
            var instId=target.instance_id||(active&&active.instance_id)||'';
            function afterInstanceReady(){
                var resolvedId=instId||selectedInstanceId();
                if(target.building){
                    document.getElementById('btnStop').setAttribute('data-build', target.number);
                    setBuilding(true);
                    updateJenkinsConsoleLink(resolvedId, target.number);
                    var stEl=document.getElementById('buildStatus');
                    if(stEl){ stEl.textContent='构建进行中 #'+target.number; stEl.className='mt-3 text-sm text-amber-600 min-h-[1.5rem]'; }
                    saveActiveBuild(resolvedId, target.number);
                    pollLogAndStatus(target.number, resolvedId);
                }else{
                    setBuilding(false);
                    clearActiveBuild();
                    loadLog(target.number, resolvedId);
                    var stEl2=document.getElementById('buildStatus');
                    if(stEl2&&target.result){
                        stEl2.textContent='最近构建 #'+target.number+': '+target.result;
                        stEl2.className='mt-3 text-sm min-h-[1.5rem] '+(target.result==='SUCCESS'?'text-green-600':'text-gray-600');
                    }
                }
            }
            if(instId){ ensureInstanceOption(instId).then(afterInstanceReady); }
            else{ afterInstanceReady(); }
        });
    }
    function refreshForInstance(){
        var listEl=document.getElementById('buildHistory');
        var logEl=document.getElementById('buildLog');
        if(!listEl||!logEl) return;
        stopPoll();
        persistInstanceChoice();
        if(!selectedInstanceId()){
            listEl.innerHTML='<li class="text-gray-500 text-sm">请选择上方 Jenkins 实例</li>';
            setBuilding(false);
            logEl.textContent='选择 Jenkins 实例后可查看本版本的构建历史与日志';
            resumeVersionBuild();
            return;
        }
        fetch('/api/jenkins-manage/instance?instance_id='+encodeURIComponent(selectedInstanceId()), {credentials:'same-origin'}).then(function(r){ return r.json(); }).then(function(d){
            INSTANCE_COMMERCIAL_DEFAULTS = (((d||{}).instance||{}).build_defaults||{}).commercial_release || {};
            renderCommercialSummary();
        });
        resumeVersionBuild();
    }
    document.getElementById('buildForm').onsubmit=function(e){
        e.preventDefault();
        if(!selectedInstanceId()){
            document.getElementById('buildStatus').textContent='请选择可用 Jenkins 实例（'+modeLabel(VERSION_MODE)+'）';
            document.getElementById('buildStatus').className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
            return false;
        }
        var btn=document.getElementById('btnTrigger');
        var btnText=document.getElementById('btnTriggerText');
        btn.disabled=true; if(btnText) btnText.textContent='提交中...';
        var params={ APP_NAME: (document.getElementById('APP_NAME')||{}).value, VERSION_NAME: (document.getElementById('VERSION_NAME')||{}).value, VERSION_CODE: (document.getElementById('VERSION_CODE')||{}).value, UNITY_VERSION: (document.getElementById('UNITY_VERSION')||{}).value, OUTPUT_BASE_DIR: (document.getElementById('OUTPUT_BASE_DIR')||{}).value, GIT_BRANCH: versionGitBranch(), CHANNEL: (document.getElementById('CHANNEL')||{}).value||'' };
        var url='/admin/build/trigger';
        var body=apiBody(params);
        if(normalizedType(VERSION_MODE)==='commercial'){
            url='/admin/build/commercial-release/trigger';
            var cPlan = buildCommercialPlanFromVersion();
            body={
                instance_id: selectedInstanceId(),
                _project_id: PROJECT_ID,
                _version_id: VERSION_ID,
                UNITY_PROJECT_PATH: cPlan.unityProjectPath || '',
                plan: cPlan
            };
        }
        fetch(url, { method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken()}, body: JSON.stringify(body), credentials:'same-origin' })
        .then(function(r){ return r.json().then(function(d){ return {ok:r.ok, status:r.status, data:d}; }); })
        .then(function(res){
            var d=res.data||{};
            if(res.ok&&d.success){
                persistInstanceChoice();
                resolveEffectiveBuildNumber(d.build_number).then(function(effectiveBuildNumber){
                    saveActiveBuild(selectedInstanceId(), effectiveBuildNumber);
                    var statusText = '已触发构建 #'+effectiveBuildNumber;
                    if(parseInt(effectiveBuildNumber,10)!==parseInt(d.build_number,10)){
                        statusText += '（已自动对齐 Jenkins 实际构建号）';
                    }
                    document.getElementById('buildStatus').textContent=statusText;
                    document.getElementById('buildStatus').className='mt-3 text-sm text-green-600 min-h-[1.5rem]';
                    document.getElementById('btnStop').setAttribute('data-build', effectiveBuildNumber);
                    setBuilding(true);
                    pollLogAndStatus(effectiveBuildNumber, selectedInstanceId());
                    loadHistory();
                    var el=document.getElementById('buildSuccessLinks');
                    if(el&&PROJECT_ID){ el.innerHTML='<a href="/admin/projects/'+PROJECT_ID+'" class="text-blue-600 hover:underline">返回项目中心</a> <a href="/admin/projects/'+PROJECT_ID+'/versions/'+VERSION_ID+'/workflow" class="text-blue-600 hover:underline">刷新本页</a>'; }
                });
            } else {
                var errMsg=d.error||d.message||('HTTP '+res.status);
                if(res.status===400&&!errMsg) errMsg='请求被拒绝（400）：请确认已选 Jenkins 实例、实例已启动，并刷新页面后重试';
                document.getElementById('buildStatus').textContent='失败: '+errMsg;
                document.getElementById('buildStatus').className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
                btn.disabled=false;
                if(btnText) btnText.textContent=normalizedType(VERSION_MODE)==='commercial'?'执行商业发布':'开始构建';
            }
        }).catch(function(){
            btn.disabled=false;
            if(btnText) btnText.textContent=normalizedType(VERSION_MODE)==='commercial'?'执行商业发布':'开始构建';
        });
        return false;
    };
    document.getElementById('btnStop').onclick=function(){
        var num=this.getAttribute('data-build'); if(!num) return;
        fetch('/api/build/'+num+'/stop', {method:'POST', headers:{'Content-Type':'application/json','X-CSRFToken':getCsrfToken()}, body: JSON.stringify(apiBody({})), credentials:'same-origin'})
        .then(r=>r.json())
        .then(function(x){
            if(x && x.success){
                stopPoll();
                clearActiveBuild();
                setBuilding(false);
                var st=document.getElementById('buildStatus');
                if(st){
                    st.textContent='已停止构建 #'+num;
                    st.className='mt-3 text-sm text-amber-600 min-h-[1.5rem]';
                }
                loadHistory();
            }else{
                var stErr=document.getElementById('buildStatus');
                if(stErr){
                    stErr.textContent='停止失败: '+((x&&x.error)||'未知错误');
                    stErr.className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
                }
            }
        })
        .catch(function(){
            var stErr=document.getElementById('buildStatus');
            if(stErr){
                stErr.textContent='停止失败: 网络异常';
                stErr.className='mt-3 text-sm text-red-600 min-h-[1.5rem]';
            }
        });
    };
    applyVersionCanonicalFields();
    applyVersionLockParams();
    renderCommercialSummary();
    var cpZh=document.getElementById('cpLangZh');
    var cpEn=document.getElementById('cpLangEn');
    function _applyCpLangBtn(){
        if(cpZh){ cpZh.className='px-2 py-1 text-[11px] rounded '+(window._cpLang==='zh'?'text-violet-700 bg-violet-100':'text-slate-500'); }
        if(cpEn){ cpEn.className='px-2 py-1 text-[11px] rounded '+(window._cpLang==='en'?'text-violet-700 bg-violet-100':'text-slate-500'); }
    }
    if(cpZh){ cpZh.onclick=function(){ window._cpLang='zh'; _applyCpLangBtn(); renderCommercialSummary(); }; }
    if(cpEn){ cpEn.onclick=function(){ window._cpLang='en'; _applyCpLangBtn(); renderCommercialSummary(); }; }
    _applyCpLangBtn();
    bindPanelState('commercialParamsPanel', 'buildwf:'+PROJECT_ID+':'+VERSION_ID+':commercial_panel', false);
    var btnTextInit=document.getElementById('btnTriggerText');
    if(btnTextInit && normalizedType(VERSION_MODE)==='commercial') btnTextInit.textContent='执行商业发布';
    loadJenkinsOptions().then(function(){ refreshForInstance(); });
    document.getElementById('jenkinsInstance').addEventListener('change', function(){
        if(document.getElementById('jenkinsInstance').disabled) return;
        persistInstanceChoice();
        updateJenkinsConsoleLink(selectedInstanceId(), '');
        refreshForInstance();
    });
    