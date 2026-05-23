


function _jmHeaders(isJson){
    var t=document.querySelector('meta[name="csrf-token"]');
    var h={};
    if(isJson) h['Content-Type']='application/json';
    if(t&&t.content) h['X-CSRFToken']=t.content;
    return h;
}
var _listFilter = 'all';
var _allInstances = [];
function filterList(type){
    _listFilter = type;
    document.querySelectorAll('#listFilterTabs [data-filter]').forEach(function(btn){
        var on = btn.getAttribute('data-filter') === type;
        btn.className = 'px-3 py-1 rounded text-xs font-medium ' + (on ? 'bg-white shadow-sm' : (btn.getAttribute('data-filter')==='commercial' ? 'text-violet-700' : 'text-slate-600'));
    });
    renderList();
}
function _typeBadge(t){
    return t==='commercial'
        ? '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-violet-100 text-violet-700">商业</span>'
        : '<span class="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-medium bg-orange-100 text-orange-700">通用</span>';
}
function renderList(){
    var tbody=document.getElementById('jenkinsInstanceList');
    var msg=document.getElementById('instanceListMsg');
    var filtered = _listFilter==='all' ? _allInstances : _allInstances.filter(function(i){ return (i.instance_type||'general')===_listFilter; });
    if(!filtered.length){ tbody.innerHTML=''; msg.textContent='暂无实例'; return; }
    var rows=filtered.map(function(i){
        var t=(i.instance_type||'general');
        var status=i.status==='running' ? '<span class="text-green-600">运行中</span>' : '<span class="text-gray-500">已停止</span>';
        var stopBtn=i.status==='running' ? `<button type="button" onclick="stopInstance('${i.id}')" class="text-red-600 hover:underline">停止</button>` : '';
        var startBtn=i.status!=='running' ? `<button type="button" onclick="startInstance('${i.id}')" class="text-green-600 hover:underline">启动</button>` : '';
        var delBtn=`<button type="button" onclick="deleteInstance('${i.id}')" class="text-gray-600 hover:underline ml-2">删除</button>`;
        var consoleUrl='http://' + window.location.hostname + ':' + i.port + '/';
        var consoleBtn = i.status==='running' ? '<a href="'+consoleUrl+'" target="_blank" class="text-blue-600 hover:underline">控制台</a>' : '<span class="text-gray-400">控制台</span>';
        var logBtn='<a href="/admin/jenkins/instance-log?instance_id='+encodeURIComponent(i.id)+'" target="_blank" class="text-blue-600 hover:underline">日志</a>';
        var editBtn='<a href="/admin/jenkins/edit?instance_id='+encodeURIComponent(i.id)+'" class="text-blue-600 hover:underline ml-1">编辑</a>';
        var taskName=(i.task_name||'').trim()||'-';
        return '<tr class="border-b"><td class="py-2">'+_typeBadge(t)+'</td><td class="py-2">'+i.port+'</td><td>'+taskName+'</td><td>'+status+'</td><td>'+ (i.added_at||'') +'</td><td>'+ (i.added_by||'') +'</td><td>'+ (i.started_at||'') +'</td><td>'+ (i.started_by||'') +'</td><td>'+consoleBtn+' '+logBtn+' '+editBtn+' '+startBtn+stopBtn+delBtn+'</td></tr>';
    }).join('');
    tbody.innerHTML=rows;
    msg.textContent='共 '+filtered.length+' 个实例';
}
function loadList(){
    fetch('/api/jenkins-manage/list', {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        _allInstances = (d && d.instances) ? d.instances : [];
        renderList();
    }).catch(function(){ document.getElementById('instanceListMsg').textContent='加载失败'; });
}
document.getElementById('instanceTypeGeneral').onclick=function(){
    document.getElementById('newInstanceType').value='general';
    this.className='px-3 py-1 rounded text-xs font-medium bg-white shadow-sm';
    var c=document.getElementById('instanceTypeCommercial');
    c.className='px-3 py-1 rounded text-xs font-medium text-violet-700';
};
document.getElementById('instanceTypeCommercial').onclick=function(){
    document.getElementById('newInstanceType').value='commercial';
    this.className='px-3 py-1 rounded text-xs font-medium bg-violet-600 text-white';
    var g=document.getElementById('instanceTypeGeneral');
    g.className='px-3 py-1 rounded text-xs font-medium text-slate-600';
};
document.getElementById('btnCheckPort').onclick=function(){
    var port=document.getElementById('newPort').value.trim();
    document.getElementById('portCheckResult').textContent='检测中…';
    fetch('/api/jenkins-manage/check-port?port='+encodeURIComponent(port), {credentials:'same-origin'}).then(r=>r.json()).then(d=>{
        document.getElementById('portCheckResult').textContent=d.ok ? d.message : d.message;
        document.getElementById('portCheckResult').className='text-sm ' + (d.ok ? 'text-green-600' : 'text-red-600');
    });
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
    var gitUrl=document.getElementById('newGitUrl')&&document.getElementById('newGitUrl').value?document.getElementById('newGitUrl').value.trim():'';
    var gitWorkspace=document.getElementById('newGitWorkspace')&&document.getElementById('newGitWorkspace').value?document.getElementById('newGitWorkspace').value.trim():'';
    var gitSshKeyPath=document.getElementById('newGitSshKeyPath')&&document.getElementById('newGitSshKeyPath').value?document.getElementById('newGitSshKeyPath').value.trim():'';
    var defaultGitBranch=document.getElementById('newDefaultGitBranch')&&document.getElementById('newDefaultGitBranch').value?document.getElementById('newDefaultGitBranch').value.trim():'';
    var branchesText=document.getElementById('newGitBranches')&&document.getElementById('newGitBranches').value?document.getElementById('newGitBranches').value.trim():'';
    var gitBranches=branchesText?branchesText.split(/\n/).map(function(s){ return s.trim(); }).filter(Boolean):[];
    var o={};
    if(appName) o.app_name=appName;
    if(versionName) o.version_name=versionName;
    if(versionCode) o.version_code=versionCode;
    if(outputBaseDir) o.output_base_dir=outputBaseDir;
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
    var instanceType=(document.getElementById('newInstanceType')&&document.getElementById('newInstanceType').value)||'general';
    body.instance_type = instanceType;
    if(taskName) body.task_name=taskName;
    if(feishuWebhook) body.feishu_webhook=feishuWebhook;
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



        (function() {
            var tokenEl = document.querySelector('meta[name="csrf-token"]');
            var csrfToken = tokenEl && tokenEl.content ? tokenEl.content : '';
            if (!csrfToken || !window.fetch || window.__adminFetchCsrfPatched) return;
            var originalFetch = window.fetch.bind(window);
            window.fetch = function(resource, init) {
                init = init || {};
                var method = String(init.method || 'GET').toUpperCase();
                var target = typeof resource === 'string' ? resource : ((resource && resource.url) || '');
                var isRelative = target && !/^https?:\/\//i.test(target);
                if (isRelative && ['POST', 'PUT', 'PATCH', 'DELETE'].indexOf(method) >= 0) {
                    var headers = new Headers(init.headers || (resource && resource.headers) || undefined);
                    if (!headers.has('X-CSRFToken')) headers.set('X-CSRFToken', csrfToken);
                    init.headers = headers;
                }
                return originalFetch(resource, init);
            };
            window.__adminFetchCsrfPatched = true;
        })();
    