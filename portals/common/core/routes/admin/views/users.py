# -*- coding: utf-8 -*-
"""Admin users management page template."""

USERS_PAGE = '''
<div class="bg-white rounded-xl shadow-sm border border-gray-100 overflow-hidden">
    <div class="px-6 py-4 border-b border-gray-100 flex flex-wrap items-center justify-between gap-3 bg-gray-50/50">
        <div class="space-y-0.5">
            <h2 class="text-lg font-semibold text-gray-800">用户列表</h2>
            <p class="text-xs text-gray-500">管理平台账号、模块权限与高风险操作权限。</p>
        </div>
        <div class="flex flex-wrap items-center gap-2">
            <div class="relative">
                <span class="pointer-events-none absolute inset-y-0 left-2.5 flex items-center text-gray-400 text-xs"><i class="fas fa-search"></i></span>
                <input type="text" id="userSearch" placeholder="搜索用户名、角色…" class="pl-8 pr-3 py-1.5 border border-gray-200 rounded-lg text-sm w-48 focus:ring-2 focus:ring-blue-500 focus:border-blue-500" />
            </div>
            <button type="button" onclick="document.getElementById('addUserForm').classList.toggle('hidden')" class="px-4 py-2.5 bg-blue-600 text-white text-sm font-medium rounded-lg hover:bg-blue-700 transition shadow-sm">+ 添加用户</button>
            <a href="/admin/users/export" class="px-4 py-2.5 bg-gray-100 text-gray-700 text-sm font-medium rounded-lg hover:bg-gray-200 transition">导出 CSV</a>
            <form id="importUserForm" class="inline" enctype="multipart/form-data">
                <input type="file" name="file" accept=".csv" id="importFile" class="hidden">
                <button type="button" onclick="document.getElementById('importFile').click()" class="px-4 py-2.5 bg-emerald-100 text-emerald-700 text-sm font-medium rounded-lg hover:bg-emerald-200 transition">批量导入</button>
            </form>
        </div>
    </div>
    <div id="addUserForm" class="px-6 py-5 border-b border-gray-100 bg-slate-50/80 hidden">
        <form onsubmit="return addUser(event)" class="space-y-5">
            <div class="grid gap-6 lg:grid-cols-3 items-start">
                <div class="lg:col-span-1 space-y-4">
                    <div>
                        <label class="block text-xs font-medium text-gray-500 mb-1">用户名</label>
                        <input type="text" id="newUsername" placeholder="用户名" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500" required>
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 mb-1">密码（至少 {{PASSWORD_MIN}} 位）</label>
                        <input type="password" id="newPassword" placeholder="密码" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500" required minlength="{{PASSWORD_MIN}}">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-gray-500 mb-1">角色</label>
                        <select id="newRole" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                            <option value="admin">管理员</option>
                            <option value="user">普通用户</option>
                        </select>
                    </div>
                    <div>
                        <button type="submit" class="w-full lg:w-auto px-4 py-2.5 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 transition shadow-sm">添加</button>
                    </div>
                </div>
                <div class="lg:col-span-2 grid gap-6 md:grid-cols-2">
                    <div id="newUserModulesWrap" class="hidden bg-white rounded-xl border border-dashed border-gray-200 px-4 py-3">
                        <label class="block text-xs font-medium text-gray-500 mb-1">模块权限</label>
                        <label class="flex items-center gap-2 text-sm mt-1">
                            <input type="checkbox" id="newUserAllModules" checked class="rounded text-blue-600">
                            <span>除用户管理外全部</span>
                        </label>
                        <div id="newUserModulesList" class="mt-2 flex flex-wrap gap-x-4 gap-y-1 text-sm"></div>
                    </div>
                    <div id="newUserScopesWrap" class="hidden bg-white rounded-xl border border-dashed border-amber-200 px-4 py-3">
                        <label class="block text-xs font-medium text-gray-500 mb-1">高级操作权限（可选）</label>
                        <p class="text-[11px] text-gray-400 mb-2">用于控制谁可以触发构建、管理 Jenkins 实例、修改系统安全等高风险操作。</p>
                        <div id="newUserScopesList" class="mt-1 flex flex-wrap gap-x-4 gap-y-1 text-sm"></div>
                    </div>
                </div>
            </div>
        </form>
    </div>
    <div class="overflow-x-auto">
        <table class="min-w-full">
            <thead class="bg-gray-50 border-b border-gray-200">
                <tr>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">用户名</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">角色</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">模块权限</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">操作权限</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">状态</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">最后登录</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">创建时间</th>
                    <th class="px-6 py-3.5 text-left text-xs font-semibold text-gray-600 uppercase tracking-wider">操作</th>
                </tr>
            </thead>
            <tbody id="usersTable" class="divide-y divide-gray-100"></tbody>
        </table>
    </div>
</div>
<div id="editUserModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-lg overflow-hidden" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-gray-100 bg-gray-50/80">
            <h3 class="text-lg font-semibold text-gray-800">编辑用户权限</h3>
            <p class="text-sm text-gray-500 mt-0.5">用户：<strong id="editUserName" class="text-gray-800"></strong></p>
        </div>
        <div class="px-6 py-5 space-y-5">
            <div>
                <label class="flex items-center gap-2 cursor-pointer p-2 rounded-lg hover:bg-gray-50">
                    <input type="checkbox" id="editAllModules" class="rounded text-blue-600 w-4 h-4">
                    <span class="font-medium text-gray-700">除用户管理外全部</span>
                </label>
                <p class="text-xs text-gray-400 mt-1 ml-6">取消勾选下方某一项时，将自动取消「全部」</p>
                <div id="editModulesList" class="mt-3 ml-6 grid grid-cols-2 gap-2"></div>
            </div>
            <div class="pt-3 border-t border-gray-100">
                <h4 class="text-xs font-semibold text-gray-500 mb-1">高级操作权限（可选）</h4>
                <p class="text-[11px] text-gray-400 mb-2">用于控制谁可以执行高风险操作，如触发构建、管理 Jenkins 实例等。</p>
                <div id="editScopesList" class="ml-1 grid grid-cols-1 gap-1 text-sm"></div>
            </div>
            <div class="pt-3 border-t border-gray-100">
                <label class="flex items-center gap-2 cursor-pointer p-2 rounded-lg hover:bg-red-50">
                    <input type="checkbox" id="editDisabled" class="rounded text-red-600 w-4 h-4">
                    <span class="text-gray-700">禁用该账号</span>
                </label>
            </div>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50/50 flex justify-end gap-2">
            <button type="button" onclick="document.getElementById('editUserModal').classList.add('hidden')" class="px-4 py-2.5 text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium text-sm transition">取消</button>
            <button type="button" onclick="saveEditUser()" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm shadow-sm transition">保存</button>
        </div>
    </div>
</div>
<div id="resetPwdModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-md overflow-hidden" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-gray-100 bg-gray-50/80">
            <h3 class="text-lg font-semibold text-gray-800">重置密码</h3>
            <p class="text-sm text-gray-500 mt-0.5">用户：<strong id="resetPwdUserName" class="text-gray-800"></strong>（密码已加密存储，无法查看，请设置新密码后告知用户）</p>
        </div>
        <div class="px-6 py-5 space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">新密码</label>
                <input type="text" id="resetPwdNew" placeholder="输入新密码" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">
                <button type="button" onclick="genRandomPwd()" class="mt-2 text-sm text-blue-600 hover:underline">随机生成并复制到剪贴板</button>
            </div>
            <p id="resetPwdTip" class="text-xs text-amber-600 bg-amber-50 border border-amber-200 rounded px-3 py-2 hidden">请复制上方新密码并告知用户，关闭后无法再查看。</p>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50/50 flex justify-end gap-2">
            <button type="button" onclick="document.getElementById('resetPwdModal').classList.add('hidden')" class="px-4 py-2.5 text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium text-sm transition">取消</button>
            <button type="button" onclick="submitResetPwd()" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm shadow-sm transition">确定重置</button>
        </div>
    </div>
</div>
<script>
var MODULE_IDS = {{MODULE_IDS}};
var MODULE_NAMES = {{MODULE_NAMES}};
var SCOPE_IDS = ["build.trigger","build.view","jenkins.manage","approval.manage","settings.manage"];
var SCOPE_NAMES = {
  "build.trigger": "触发/停止构建",
  "build.view": "查看构建历史与日志",
  "jenkins.manage": "管理 Jenkins 实例（启动/停止/删除、环境部署）",
  "approval.manage": "审批发布与敏感操作",
  "settings.manage": "修改系统与安全设置"
};
document.getElementById('newRole').onchange=function(){
    var wrap=document.getElementById('newUserModulesWrap');
    var scopeWrap=document.getElementById('newUserScopesWrap');
    wrap.classList.toggle('hidden', this.value!=='user');
    if(scopeWrap) scopeWrap.classList.toggle('hidden', this.value!=='user');
    if(this.value==='user'){
        var list=document.getElementById('newUserModulesList');
        list.innerHTML=MODULE_IDS.map(function(id){ return '<label class="flex items-center gap-1"><input type="checkbox" class="mod-cb" value="'+id+'"> '+MODULE_NAMES[id]+'</label>'; }).join('');
        var scopeList=document.getElementById('newUserScopesList');
        if(scopeList && scopeList.children.length===0){
            SCOPE_IDS.forEach(function(id){
                var lb=document.createElement('label');
                lb.className='flex items-center gap-1';
                lb.innerHTML='<input type="checkbox" class="new-scope-cb" value="'+id+'"> '+(SCOPE_NAMES[id]||id);
                scopeList.appendChild(lb);
            });
        }
    }
};
document.getElementById('importFile').onchange=function(){
    if(!this.files||!this.files[0]) return;
    var fd=new FormData();
    fd.append('file', this.files[0]);
    fetch('/admin/users/import', { method:'POST', body: fd, credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){ alert(d.error||('导入完成：新增 '+d.created+' 人，跳过 '+d.skipped+' 条')); if(!d.error) loadUsers(); this.value=''; }.bind(this));
};
function collectNewUserModules(){
    if(document.getElementById('newUserAllModules').checked) return ['*'];
    return Array.from(document.querySelectorAll('#newUserModulesList .mod-cb:checked')).map(function(c){ return c.value; });
}
function collectNewUserScopes(){
    return Array.from(document.querySelectorAll('#newUserScopesList .new-scope-cb:checked')).map(function(c){ return c.value; });
}
var allUsersCache = [];
function renderUsersTable(users){
    var t=document.getElementById('usersTable');
    var q=(document.getElementById('userSearch')||{}).value||'';
    q=q.trim().toLowerCase();
    var list = q ? users.filter(function(u){ return (u.username||'').toLowerCase().indexOf(q)>=0 || (u.role||'').toLowerCase().indexOf(q)>=0; }) : users;
    var rows = list.map(function(u, i){
        var permText = u.role==='user' ? (u.allowed_modules&&u.allowed_modules.indexOf('*')>=0 ? '全部(除用户管理)' : (u.allowed_modules||[]).join(', ') || '无') : '-';
        var scopeText = u.role==='user' ? ((u.allowed_scopes||[]).length ? (u.allowed_scopes||[]).map(function(s){ return (SCOPE_NAMES[s]||s).slice(0,8); }).join(', ') : '-') : '-';
        var status = u.disabled ? '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-red-100 text-red-700">已禁用</span>' : '<span class="inline-flex items-center px-2 py-0.5 rounded text-xs font-medium bg-emerald-100 text-emerald-700">正常</span>';
        var lastLoginStr = (u.last_login||'').slice(0,19).replace('T',' ') || '-';
        var actions = [];
        if(u.role!=='super_admin' && u.username!=='admin'){
            actions.push('<button onclick="editUser(\\''+u.username+'\\')" class="px-2 py-1 text-sm text-blue-600 hover:bg-blue-50 rounded">编辑权限</button>');
            actions.push('<button onclick="openResetPwd(\\''+u.username+'\\')" class="px-2 py-1 text-sm text-violet-600 hover:bg-violet-50 rounded">重置密码</button>');
            actions.push(u.disabled ? '<button onclick="toggleUser(\\''+u.username+'\\', false)" class="px-2 py-1 text-sm text-emerald-600 hover:bg-emerald-50 rounded">启用</button>' : '<button onclick="toggleUser(\\''+u.username+'\\', true)" class="px-2 py-1 text-sm text-amber-600 hover:bg-amber-50 rounded">禁用</button>');
            actions.push('<button onclick="deleteUser(\\''+u.username+'\\')" class="px-2 py-1 text-sm text-red-600 hover:bg-red-50 rounded">删除</button>');
        }
        var rowClass = (i%2===0) ? 'bg-white' : 'bg-gray-50/50';
        var dateStr = (u.created_at||'').slice(0,19).replace('T',' ');
        return '<tr class="'+rowClass+' hover:bg-blue-50/30" data-username="'+u.username+'"><td class="px-6 py-3.5 font-medium text-gray-900">'+u.username+'</td><td class="px-6 py-3.5 text-sm text-gray-600">'+u.role+'</td><td class="px-6 py-3.5 text-sm text-gray-600">'+permText+'</td><td class="px-6 py-3.5 text-xs text-gray-500 max-w-[140px]" title="'+((u.allowed_scopes||[]).join(', ')||'-')+'">'+scopeText+'</td><td class="px-6 py-3.5">'+status+'</td><td class="px-6 py-3.5 text-sm text-gray-500">'+lastLoginStr+'</td><td class="px-6 py-3.5 text-sm text-gray-500">'+dateStr+'</td><td class="px-6 py-3.5"><span class="inline-flex flex-wrap gap-1">'+actions.join('')+'</span></td></tr>';
    }).join('');
    t.innerHTML = rows;
}
function loadUsers(){
    fetch('/admin/users/list').then(r=>r.json()).then(d=>{
        allUsersCache = d.users||[];
        renderUsersTable(allUsersCache);
    });
}
var searchEl = document.getElementById('userSearch'); if(searchEl) searchEl.oninput = function(){ renderUsersTable(allUsersCache); };
var resetPwdUsername = null;
function openResetPwd(name){
    resetPwdUsername=name;
    document.getElementById('resetPwdUserName').textContent=name;
    document.getElementById('resetPwdNew').value='';
    document.getElementById('resetPwdTip').classList.add('hidden');
    document.getElementById('resetPwdModal').classList.remove('hidden');
}
function genRandomPwd(){
    var s='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789';
    var p='';
    for(var i=0;i<12;i++) p+=s.charAt(Math.floor(Math.random()*s.length));
    var el=document.getElementById('resetPwdNew');
    el.value=p;
    if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(p).then(function(){ alert('已生成并复制到剪贴板：'+p); }); }
    else { alert('已生成新密码（请手动复制）：'+p); }
    document.getElementById('resetPwdTip').classList.remove('hidden');
}
function submitResetPwd(){
    if(!resetPwdUsername) return;
    var pwd=document.getElementById('resetPwdNew').value.trim();
    if(!pwd){ alert('请输入新密码'); return; }
    fetch('/admin/users/reset-password', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username: resetPwdUsername, new_password: pwd })}).then(r=>r.json()).then(d=>{ alert(d.error||'密码已重置'); if(!d.error) { document.getElementById('resetPwdModal').classList.add('hidden'); loadUsers(); } });
}
function addUser(e){ e.preventDefault();
    var role=document.getElementById('newRole').value;
    var payload={ username: document.getElementById('newUsername').value, password: document.getElementById('newPassword').value, role: role };
    if(role==='user'){
        payload.allowed_modules=collectNewUserModules();
        var scopes=collectNewUserScopes();
        if(scopes.length) payload.allowed_scopes=scopes;
    }
    fetch('/admin/users/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(r=>r.json()).then(d=>{ alert(d.error||'添加成功'); if(!d.error) { loadUsers(); document.getElementById('addUserForm').classList.add('hidden'); } });
    return false;
}
var editingUsername = null;
function editUser(name){
    editingUsername=name;
    fetch('/admin/users/get/'+encodeURIComponent(name)).then(r=>r.json()).then(d=>{
        if(!d.user){ alert('用户不存在'); return; }
        var u=d.user;
        document.getElementById('editUserName').textContent=u.username;
        document.getElementById('editAllModules').checked = u.allowed_modules&&u.allowed_modules.indexOf('*')>=0;
        MODULE_IDS.forEach(function(id){
            var cb=document.querySelector('#editModulesList input[value="'+id+'"]');
            if(cb) cb.checked = u.allowed_modules&&(u.allowed_modules.indexOf('*')>=0||u.allowed_modules.indexOf(id)>=0);
        });
        // 高级操作权限
        var scopesWrap = document.getElementById('editScopesList');
        if(scopesWrap && scopesWrap.children.length === 0){
            SCOPE_IDS.forEach(function(id){
                var label=document.createElement('label');
                label.className='flex items-center gap-2 cursor-pointer py-0.5 rounded hover:bg-gray-50';
                label.innerHTML='<input type="checkbox" value="'+id+'" class="rounded text-indigo-600 w-4 h-4 edit-scope-cb"> <span class="text-sm text-gray-700">'+(SCOPE_NAMES[id]||id)+'</span>';
                scopesWrap.appendChild(label);
            });
        }
        var scopes = u.allowed_scopes||[];
        document.querySelectorAll('#editScopesList .edit-scope-cb').forEach(function(cb){
            cb.checked = scopes.indexOf(cb.value) >= 0;
        });
        document.getElementById('editDisabled').checked=!!u.disabled;
        document.getElementById('editUserModal').classList.remove('hidden');
    });
}
document.getElementById('editAllModules').onchange=function(){
    document.querySelectorAll('#editModulesList input').forEach(function(cb){ cb.checked=this.checked; }.bind(this));
};
function saveEditUser(){
    if(!editingUsername) return;
    var allCb = document.getElementById('editAllModules');
    var listCbs = document.querySelectorAll('#editModulesList input');
    var allowed = allCb.checked ? ['*'] : Array.from(listCbs).filter(function(c){ return c.checked; }).map(function(c){ return c.value; });
    var disabled = document.getElementById('editDisabled').checked;
    var scopes = Array.from(document.querySelectorAll('#editScopesList .edit-scope-cb:checked')).map(function(c){ return c.value; });
    fetch('/admin/users/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username: editingUsername, allowed_modules: allowed, allowed_scopes: scopes, disabled: disabled })}).then(r=>r.json()).then(d=>{ alert(d.error||'已保存'); if(!d.error) { loadUsers(); document.getElementById('editUserModal').classList.add('hidden'); } });
}
function toggleUser(name, disable){
    fetch('/admin/users/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username: name, disabled: disable })}).then(r=>r.json()).then(d=>{ alert(d.error||'已更新'); if(!d.error) loadUsers(); });
}
function deleteUser(name){
    if(!confirm('确定删除用户 '+name+'？')) return;
    fetch('/admin/users/delete/'+encodeURIComponent(name), { method:'DELETE' }).then(r=>r.json()).then(d=>{ alert(d.error||'已删除'); if(!d.error) loadUsers(); });
}
(function(){
    var list=document.getElementById('editModulesList');
    MODULE_IDS.forEach(function(id){ list.innerHTML+='<label class="flex items-center gap-2 cursor-pointer py-1 rounded hover:bg-gray-50"><input type="checkbox" value="'+id+'" class="rounded text-blue-600 w-4 h-4 edit-mod-cb"> <span class="text-sm text-gray-700">'+MODULE_NAMES[id]+'</span></label>'; });
    document.querySelectorAll('#editModulesList input').forEach(function(cb){
        cb.addEventListener('change', function(){ if(!this.checked) document.getElementById('editAllModules').checked=false; });
    });
})();
loadUsers();
</script>
'''


def render_users_page(password_min: int) -> str:
    import json

    from services.authz import ADMIN_MODULES

    module_ids = json.dumps([m[0] for m in ADMIN_MODULES if m[0] != "user_management"])
    module_names = json.dumps(
        dict((m[0], m[1]) for m in ADMIN_MODULES if m[0] != "user_management")
    )
    return (
        USERS_PAGE.replace("{{PASSWORD_MIN}}", str(password_min))
        .replace("{{MODULE_IDS}}", module_ids)
        .replace("{{MODULE_NAMES}}", module_names)
    )
