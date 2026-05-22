
function _jmHeaders(isJson){
    var t=document.querySelector('meta[name="csrf-token"]');
    var h={};
    if(isJson) h['Content-Type']='application/json';
    if(t&&t.content) h['X-CSRFToken']=t.content;
    return h;
}
function loadList(){
    fetch('/api/jenkins-manage/list', {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        var tbody=document.getElementById('jenkinsInstanceList');
        var msg=document.getElementById('instanceListMsg');
        if(!d||!d.instances){ tbody.innerHTML=''; msg.textContent='No instances'; return; }
        var rows=d.instances.map(function(i){
            var status=i.status==='running' ? '<span class="text-green-600">running</span>' : '<span class="text-gray-500">stopped</span>';
            var stopBtn=i.status==='running' ? '<button type="button" onclick="stopInstance(\''+i.id+'\')" class="text-red-600 hover:underline">Stop</button>' : '';
            var startBtn=i.status!=='running' ? '<button type="button" onclick="startInstance(\''+i.id+'\')" class="text-green-600 hover:underline">Start</button>' : '';
            var delBtn='<button type="button" onclick="deleteInstance(\''+i.id+'\')" class="text-gray-600 hover:underline ml-2">Delete</button>';
            var logBtn='<a href="/admin/jenkins/instance-log?instance_id='+encodeURIComponent(i.id)+'" target="_blank" class="text-blue-600 hover:underline">Log</a>';
            var editBtn='<a href="/admin/jenkins/edit?instance_id='+encodeURIComponent(i.id)+'" class="text-blue-600 hover:underline ml-1">Edit</a>';
            var taskName=(i.task_name||'').trim()||'-';
            return '<tr class="border-b"><td class="py-2">'+i.port+'</td><td>'+taskName+'</td><td>'+status+'</td><td>'+ (i.added_at||'') +'</td><td>'+ (i.added_by||'') +'</td><td>'+ (i.started_at||'') +'</td><td>'+ (i.started_by||'') +'</td><td>'+logBtn+' '+editBtn+' '+startBtn+stopBtn+delBtn+'</td></tr>';
        }).join('');
        tbody.innerHTML=rows;
        msg.textContent='Total '+d.instances.length+' instances';
    }).catch(function(){ document.getElementById('instanceListMsg').textContent='Load failed'; });
}
document.getElementById('btnCheckPort').onclick=function(){
    var port=document.getElementById('newPort').value.trim();
    document.getElementById('portCheckResult').textContent='检测中…';
    fetch('/api/jenkins-manage/check-port?port='+encodeURIComponent(port), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        document.getElementById('portCheckResult').textContent=d.ok ? d.message : d.message;
        document.getElementById('portCheckResult').className='text-sm ' + (d.ok ? 'text-green-600' : 'text-red-600');
    });
};
document.getElementById('btnDetectUnityVersions').onclick=function(){
    var btn=document.getElementById('btnDetectUnityVersions');
    var sel=document.getElementById('detectedUnityVersions');
    var tip=document.getElementById('unityDetectResult');
    if(sel){ sel.innerHTML='<option value="">Detecting...</option>'; }
    if(tip){ tip.textContent='Detecting local Unity installations...'; tip.className='text-xs text-gray-500 mt-1'; }
    if(btn){ btn.disabled=true; }
    fetch('/api/jenkins-manage/detect-unity', {credentials:'same-origin'})
    .then(function(r){ if(!r.ok) throw new Error('HTTP '+r.status); return r.json(); })
    .then(function(d){
        var items=(d&&d.versions)||[];
        if(!sel) return;
        if(!items.length){
            sel.innerHTML='<option value="">No Unity detected</option>';
            if(tip){ tip.textContent='No Unity installation detected.'; tip.className='text-xs text-amber-600 mt-1'; }
            return;
        }
        sel.innerHTML='';
        items.forEach(function(it){
            var v=(it&&it.version)||'';
            var p=(it&&it.path)||'';
            var line=v+(p?(','+p):'');
            var op=document.createElement('option');
            op.value=line;
            op.textContent=v+(p?('  ['+p+']'):'');
            sel.appendChild(op);
        });
        if(tip){ tip.textContent='Detected '+items.length+' Unity version(s).'; tip.className='text-xs text-green-600 mt-1'; }
    })
    .catch(function(e){
        if(sel){ sel.innerHTML='<option value="">Detect failed</option>'; }
        if(tip){ tip.textContent='Detect failed: '+(e&&e.message?e.message:'unknown'); tip.className='text-xs text-red-600 mt-1'; }
    })
    .finally(function(){ if(btn){ btn.disabled=false; } });
};
document.getElementById('btnUseDetectedUnity').onclick=function(){
    var sel=document.getElementById('detectedUnityVersions');
    var ta=document.getElementById('newUnityVersions');
    if(!sel||!ta||!sel.value) return;
    var line=sel.value.trim();
    if(!line) return;
    var rows=(ta.value||'').split(/\\n/).map(function(x){ return x.trim(); }).filter(Boolean);
    if(rows.indexOf(line)<0){ rows.push(line); }
    ta.value=rows.join('\\n');
};
document.getElementById('btnValidateGit').onclick=function(){
    var gitUrl=document.getElementById('newGitUrl')&&document.getElementById('newGitUrl').value?document.getElementById('newGitUrl').value.trim():'';
    var gitWorkspace=document.getElementById('newGitWorkspace')&&document.getElementById('newGitWorkspace').value?document.getElementById('newGitWorkspace').value.trim():'';
    var gitSshKeyPath=document.getElementById('newGitSshKeyPath')&&document.getElementById('newGitSshKeyPath').value?document.getElementById('newGitSshKeyPath').value.trim():'';
    var el=document.getElementById('gitValidateResult');
    el.textContent='验证中…'; el.className='text-sm text-gray-500';
    fetch('/api/jenkins-manage/validate-git', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({git_url:gitUrl, git_workspace:gitWorkspace, git_ssh_key_path:gitSshKeyPath})})
    .then(r=>r.json()).then(d=>{
        if(d.ok){ el.textContent='Git 配置有效'; el.className='text-sm text-green-600'; }
        else{ el.textContent=(d.errors&&d.errors.length)?d.errors.join('；'):'配置有误'; el.className='text-sm text-red-600'; }
    }).catch(function(){ el.textContent='验证请求失败'; el.className='text-sm text-red-600'; });
};
function collectBuildDefaults(){
    var appName=document.getElementById('newAppName')&&document.getElementById('newAppName').value?document.getElementById('newAppName').value.trim():'';
    var versionName=document.getElementById('newVersionName')&&document.getElementById('newVersionName').value?document.getElementById('newVersionName').value.trim():'';
    var versionCode=document.getElementById('newVersionCode')&&document.getElementById('newVersionCode').value?document.getElementById('newVersionCode').value.trim():'';
    var outputBaseDir=document.getElementById('newOutputBaseDir')&&document.getElementById('newOutputBaseDir').value?document.getElementById('newOutputBaseDir').value.trim():'';
    var unityText=document.getElementById('newUnityVersions')&&document.getElementById('newUnityVersions').value?document.getElementById('newUnityVersions').value.trim():'';
    var unityVersions=[];
    if(unityText){ unityText.split(/\\n/).forEach(function(line){ var t=line.trim(); if(!t) return; var parts=t.split(','); unityVersions.push({version: parts[0].trim(), path: parts[1]?parts[1].trim():''}); }); }
    var gitUrl=document.getElementById('newGitUrl')&&document.getElementById('newGitUrl').value?document.getElementById('newGitUrl').value.trim():'';
    var gitWorkspace=document.getElementById('newGitWorkspace')&&document.getElementById('newGitWorkspace').value?document.getElementById('newGitWorkspace').value.trim():'';
    var gitSshKeyPath=document.getElementById('newGitSshKeyPath')&&document.getElementById('newGitSshKeyPath').value?document.getElementById('newGitSshKeyPath').value.trim():'';
    var defaultGitBranch=document.getElementById('newDefaultGitBranch')&&document.getElementById('newDefaultGitBranch').value?document.getElementById('newDefaultGitBranch').value.trim():'';
    var branchesText=document.getElementById('newGitBranches')&&document.getElementById('newGitBranches').value?document.getElementById('newGitBranches').value.trim():'';
    var gitBranches=branchesText?branchesText.split(/\\n/).map(function(s){ return s.trim(); }).filter(Boolean):[];
    var o={};
    if(appName) o.app_name=appName;
    if(versionName) o.version_name=versionName;
    if(versionCode) o.version_code=versionCode;
    if(outputBaseDir) o.output_base_dir=outputBaseDir;
    if(unityVersions.length) o.unity_versions=unityVersions;
    if(gitUrl) o.git_url=gitUrl;
    if(gitWorkspace) o.git_workspace=gitWorkspace;
    if(gitSshKeyPath) o.git_ssh_key_path=gitSshKeyPath;
    if(defaultGitBranch) o.default_git_branch=defaultGitBranch;
    if(gitBranches.length) o.git_branches=gitBranches;
    return Object.keys(o).length?o:null;
}
document.getElementById('btnStartJenkins').onclick=function(){
    var port=document.getElementById('newPort').value.trim();
    var taskName=(document.getElementById('newTaskName')&&document.getElementById('newTaskName').value) ? document.getElementById('newTaskName').value.trim() : '';
    var feishuWebhook=(document.getElementById('newFeishuWebhook')&&document.getElementById('newFeishuWebhook').value) ? document.getElementById('newFeishuWebhook').value.trim() : '';
    var el=document.getElementById('startResult');
    el.textContent='启动中…';
    var body={port: parseInt(port,10)};
    if(taskName) body.task_name=taskName;
    if(feishuWebhook) body.feishu_webhook=feishuWebhook;
    var bd=collectBuildDefaults();
    if(bd) body.build_defaults=bd;
    fetch('/api/jenkins-manage/start', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify(body)})
    .then(r=>r.json()).then(d=>{
        if(d.success){ el.textContent='已启动，实例 ID: '+d.instance_id; el.className='mt-2 text-sm text-green-600'; loadList(); }
        else{ el.textContent=d.error||'启动失败'; el.className='mt-2 text-sm text-red-600'; }
    }).catch(function(){ document.getElementById('startResult').textContent='请求失败'; });
};
function startInstance(id){
    fetch('/api/jenkins-manage/start-instance', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({instance_id: id})})
    .then(r=>r.json()).then(d=>{ if(d.success){ loadList(); } else{ alert(d.error||'启动失败'); } });
}
function stopInstance(id){
    if(!confirm('确定停止该 Jenkins？')) return;
    fetch('/api/jenkins-manage/stop', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({instance_id: id})})
    .then(r=>r.json()).then(d=>{ if(d.success) loadList(); else alert(d.error||'停止失败'); });
}
function deleteInstance(id){
    if(!confirm('确定从列表删除该实例？（不会删除 JENKINS_HOME 数据）')) return;
    fetch('/api/jenkins-manage/delete', {method:'POST', headers:_jmHeaders(true), credentials:'same-origin', body: JSON.stringify({instance_id: id})})
    .then(r=>r.json()).then(d=>{ if(d.success) loadList(); else alert(d.error||'删除失败'); });
}
document.getElementById('btnDeployEnv').onclick=function(){
    var logEl=document.getElementById('deployLog');
    logEl.classList.remove('hidden');
    logEl.textContent='部署已开始，请稍候…';
    fetch('/api/jenkins-manage/deploy-env', {method:'POST', headers:_jmHeaders(false), credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        if(d.log_path) fetch('/api/jenkins-manage/deploy-log?path='+encodeURIComponent(d.log_path), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ logEl.textContent=t||'无输出'; setInterval(function(){ fetch('/api/jenkins-manage/deploy-log?path='+encodeURIComponent(d.log_path), {credentials:'same-origin'}).then(r=>r.text()).then(t=>{ logEl.textContent=t||'无输出'; logEl.scrollTop=logEl.scrollHeight; }); }, 2000); });
        else logEl.textContent=d.error||'执行失败';
    }).catch(function(){ logEl.textContent='请求失败'; });
};
loadList();
