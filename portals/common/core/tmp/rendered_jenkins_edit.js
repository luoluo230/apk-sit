
(function(){
var instanceId = "10477171";
function _jmHeaders(isJson){
    var t=document.querySelector('meta[name="csrf-token"]');
    var h={};
    if(isJson) h['Content-Type']='application/json';
    if(t&&t.content) h['X-CSRFToken']=t.content;
    return h;
}
function setEditResult(msg, isError){
    var el = document.getElementById('editResult');
    if(el){ el.textContent = msg; el.className = 'mt-3 px-3 py-2 rounded text-sm font-medium min-h-[2.5rem] border ' + (isError ? 'bg-red-100 text-red-700 border-red-300' : 'bg-green-100 text-green-700 border-green-300'); el.setAttribute('role', 'status'); try{ el.scrollIntoView({ behavior: 'smooth', block: 'nearest' }); }catch(e){} }
    else{ alert(msg); }
}
function doSave(){
    try{
        setEditResult('保存中…', false);
        var payload = { instance_id: instanceId, task_name: document.getElementById('editTaskName').value.trim(), feishu_webhook: document.getElementById('editFeishuWebhook').value.trim() };
        fetch('/api/jenkins-manage/update', { method: 'POST', headers: _jmHeaders(true), credentials: 'same-origin', body: JSON.stringify(payload) })
        .then(function(r){ return r.json().then(function(d){ return { ok: r.ok, data: d }; }).catch(function(){ return { ok: false, data: { error: '响应格式错误' } }; }); })
        .then(function(x){ if(x.data && x.data.success) setEditResult('已保存', false); else setEditResult(x.data && x.data.error ? x.data.error : '保存失败', true); })
        .catch(function(e){ setEditResult('请求失败: ' + (e && e.message ? e.message : '请检查网络'), true); });
    }catch(e){ setEditResult('操作异常: ' + (e.message || ''), true); }
}
var btnSave = document.getElementById('btnSaveEdit');
if(btnSave) btnSave.onclick = doSave;
})();



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
    