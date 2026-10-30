# -*- coding: utf-8 -*-
"""Admin users management page template."""

USERS_PAGE = '''
<header class="pm-page-head">
    <div class="pm-page-head-copy"><div>
        <h1>成员</h1>
        <p>管理平台账号、模块权限与高风险操作权限。</p>
    </div></div>
    <div class="pm-page-head-actions">
        <button type="button" class="pm-btn pm-btn--primary" onclick="document.getElementById('addUserForm').classList.toggle('is-hidden')">添加用户</button>
        <a class="pm-btn" href="/admin/users/export">导出 CSV</a>
        <form id="importUserForm" class="inline" enctype="multipart/form-data">
            <input type="file" name="file" accept=".csv" id="importFile" class="hidden">
            <button type="button" class="pm-btn" onclick="document.getElementById('importFile').click()">批量导入</button>
        </form>
    </div>
</header>
<div class="pm-filter-bar">
    <div class="pm-filter-search"><input type="text" id="userSearch" placeholder="搜索用户名、角色…"></div>
</div>
<div id="addUserForm" class="studio-config-panel is-hidden">
    <h3>添加用户</h3>
    <form onsubmit="return addUser(event)" class="studio-form-grid">
        <div class="studio-form-field"><label>用户名</label><input type="text" id="newUsername" placeholder="用户名" required></div>
        <div class="studio-form-field"><label>密码（至少 {{PASSWORD_MIN}} 位）</label><input type="password" id="newPassword" placeholder="密码" required minlength="{{PASSWORD_MIN}}"></div>
        <div class="studio-form-field"><label>角色</label>
            <select id="newRole"><option value="admin">管理员</option><option value="user">普通用户</option></select>
        </div>
        <div class="studio-form-field"><label>&nbsp;</label><button type="submit" class="pm-btn pm-btn--primary">添加</button></div>
        <div id="newUserModulesWrap" class="studio-form-field studio-form-field--full is-hidden">
            <label>模块权限</label>
            <label class="flex items-center gap-2 text-sm"><input type="checkbox" id="newUserAllModules" checked><span>除用户管理外全部</span></label>
            <div id="newUserModulesList" class="flex flex-wrap gap-3 text-sm mt-2"></div>
        </div>
        <div id="newUserScopesWrap" class="studio-form-field studio-form-field--full is-hidden">
            <label>高级操作权限（可选）</label>
            <p class="text-xs text-gray-500">控制构建、Jenkins、审批与系统安全等高风险操作。</p>
            <div id="newUserScopesList" class="flex flex-wrap gap-3 text-sm mt-2"></div>
        </div>
    </form>
</div>
<div class="pm-table-panel overflow-x-auto">
    <table class="pm-table">
        <thead>
            <tr>
                <th>用户名</th><th>角色</th><th>模块权限</th><th>操作权限</th>
                <th>状态</th><th>最后登录</th><th>创建时间</th><th>操作</th>
            </tr>
        </thead>
        <tbody id="usersTable"></tbody>
    </table>
</div>
<div id="editUserModal" class="pm-modal-root is-hidden" onclick="if(event.target===this) this.classList.add('is-hidden')">
    <div class="pm-modal-mask"></div>
    <div class="pm-modal pm-modal--720" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>编辑用户权限</h2><p>用户：<strong id="editUserName"></strong></p></div></div>
        <div class="pm-modal-body">
            <div class="studio-form-field">
                <label>角色</label>
                <select id="editRole">
                    <option value="user">普通用户（按模块授权）</option>
                    <option value="admin">管理员（全模块，不含用户管理敏感操作策略）</option>
                    <option value="super_admin">超级管理员（全部权限）</option>
                </select>
                <p class="studio-hint">超级管理员/管理员默认拥有全部模块；普通用户按下方模块与操作勾选。</p>
            </div>
            <div id="editPermPanels" class="studio-form-field mt-3">
                <label class="flex items-center gap-2"><input type="checkbox" id="editAllModules"><span>除用户管理外全部模块</span></label>
                <p class="studio-hint">按业务域勾选；取消任意模块时会自动取消「全部」。</p>
                <div id="editModulesList" class="perm-module-grid mt-2"></div>
                <label class="mt-3">高风险操作（按能力）</label>
                <p class="studio-hint">与模块独立：例如有「构建管理」模块后，仍需勾选「触发构建」才能点构建。</p>
                <div id="editScopesList" class="perm-scope-list"></div>
            </div>
            <div class="studio-form-field mt-3">
                <label class="flex items-center gap-2"><input type="checkbox" id="editDisabled"><span>禁用该账号</span></label>
            </div>
        </div>
        <div class="pm-modal-foot">
            <button type="button" class="pm-btn" onclick="document.getElementById('editUserModal').classList.add('is-hidden')">取消</button>
            <button type="button" class="pm-btn pm-btn--primary" onclick="saveEditUser()">保存</button>
        </div>
    </div>
</div>
<div id="resetPwdModal" class="pm-modal-root is-hidden" onclick="if(event.target===this) this.classList.add('is-hidden')">
    <div class="pm-modal-mask"></div>
    <div class="pm-modal pm-modal--480" onclick="event.stopPropagation()">
        <div class="pm-modal-head"><div><h2>重置密码</h2><p>用户：<strong id="resetPwdUserName"></strong></p></div></div>
        <div class="pm-modal-body">
            <div class="studio-form-field">
                <label>新密码</label>
                <input type="text" id="resetPwdNew" placeholder="输入新密码">
                <button type="button" class="pm-btn pm-btn--compact mt-2" onclick="genRandomPwd()">随机生成并复制</button>
            </div>
            <p id="resetPwdTip" class="studio-feedback is-error is-hidden mt-2">请复制上方新密码并告知用户，关闭后无法再查看。</p>
        </div>
        <div class="pm-modal-foot">
            <button type="button" class="pm-btn" onclick="document.getElementById('resetPwdModal').classList.add('is-hidden')">取消</button>
            <button type="button" class="pm-btn pm-btn--primary" onclick="submitResetPwd()">确定重置</button>
        </div>
    </div>
</div>
<script>
var MODULE_IDS = {{MODULE_IDS}};
var MODULE_NAMES = {{MODULE_NAMES}};
var CURRENT_USER = {{CURRENT_USER}};
var MODULE_GROUPS = [
  { title: "交付与构建", ids: ["projects","build","versions","jenkins"] },
  { title: "协作与治理", ids: ["notifications","approval","docs","audit_log","reports"] },
  { title: "运营与运维", ids: ["community","gm_ops","dashboard"] },
  { title: "系统", ids: ["system_settings"] }
];
var SCOPE_IDS = ["build.trigger","build.view","jenkins.manage","approval.manage","settings.manage"];
var SCOPE_NAMES = {
  "build.trigger": "触发/停止构建",
  "build.view": "查看构建历史与日志",
  "jenkins.manage": "管理 Jenkins 实例（启动/停止/删除、环境部署）",
  "approval.manage": "审批发布与敏感操作",
  "settings.manage": "修改系统与安全设置"
};
var SCOPE_HINTS = {
  "build.trigger": "对应模块：构建管理",
  "build.view": "对应模块：构建管理",
  "jenkins.manage": "对应模块：Jenkins 实例管理",
  "approval.manage": "对应模块：审批与发布管控",
  "settings.manage": "对应模块：系统与安全设置"
};
document.getElementById('newRole').onchange=function(){
    var wrap=document.getElementById('newUserModulesWrap');
    var scopeWrap=document.getElementById('newUserScopesWrap');
    wrap.classList.toggle('is-hidden', this.value!=='user');
    if(scopeWrap) scopeWrap.classList.toggle('is-hidden', this.value!=='user');
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
        var roleKey = u.role || 'user';
        var roleLabel = roleKey === 'super_admin' ? '超级管理员' : (roleKey === 'admin' ? '管理员' : '普通用户');
        var roleHtml = '<span class="pm-role-tag pm-role-tag--'+roleKey+'">'+roleLabel+'</span>';
        var permText = u.role==='user' ? (u.allowed_modules&&u.allowed_modules.indexOf('*')>=0 ? '全部(除用户管理)' : (u.allowed_modules||[]).join(', ') || '无') : '全部';
        var scopeText = u.role==='user' ? ((u.allowed_scopes||[]).length ? (u.allowed_scopes||[]).map(function(s){ return (SCOPE_NAMES[s]||s).slice(0,8); }).join(', ') : '-') : '全部';
        var status = u.disabled ? '<span class="pm-tag pm-tag--danger">已禁用</span>' : '<span class="pm-tag pm-tag--success">正常</span>';
        var lastLoginStr = (u.last_login||'').slice(0,19).replace('T',' ') || '-';
        var actions = [];
        var isBootstrap = u.username === 'admin';
        var isSelf = CURRENT_USER && u.username === CURRENT_USER;
        if (!isBootstrap) {
            actions.push('<button type="button" onclick="editUser(\\''+u.username+'\\')" class="pm-btn pm-btn--compact pm-btn--primary">权限</button>');
            var more = ['<button type="button" onclick="openResetPwd(\\''+u.username+'\\')" class="pm-btn pm-btn--compact">重置密码</button>'];
            if (!isSelf) {
                more.push(u.disabled
                    ? '<button type="button" onclick="toggleUser(\\''+u.username+'\\', false)" class="pm-btn pm-btn--compact">启用</button>'
                    : '<button type="button" onclick="toggleUser(\\''+u.username+'\\', true)" class="pm-btn pm-btn--compact">禁用</button>');
                more.push('<button type="button" onclick="deleteUser(\\''+u.username+'\\')" class="pm-btn pm-btn--compact pm-btn--danger">删除</button>');
            } else {
                more.push('<span class="studio-hint">当前账号不可禁用/删除</span>');
            }
            actions.push('<details class="pm-row-more"><summary>更多</summary><div class="pm-row-more-menu">'+more.join('')+'</div></details>');
        } else {
            actions.push('<span class="studio-hint">受保护</span>');
        }
        var dateStr = (u.created_at||'').slice(0,19).replace('T',' ');
        return '<tr data-username="'+u.username+'"><td><strong>'+u.username+'</strong></td><td>'+roleHtml+'</td><td title="'+permText+'">'+permText+'</td><td title="'+((u.allowed_scopes||[]).join(', ')||scopeText)+'">'+scopeText+'</td><td>'+status+'</td><td>'+lastLoginStr+'</td><td>'+dateStr+'</td><td><div class="pm-table-actions">'+actions.join('')+'</div></td></tr>';
    }).join('') || '<tr><td colspan="8"><div class="pm-placeholder-page"><h2>暂无成员</h2><p>点击右上角「添加用户」创建账号。</p></div></td></tr>';
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
    document.getElementById('resetPwdTip').classList.add('is-hidden');
    document.getElementById('resetPwdModal').classList.remove('is-hidden');
}
function genRandomPwd(){
    var s='ABCDEFGHJKLMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789';
    var p='';
    for(var i=0;i<12;i++) p+=s.charAt(Math.floor(Math.random()*s.length));
    var el=document.getElementById('resetPwdNew');
    el.value=p;
    if(navigator.clipboard&&navigator.clipboard.writeText){ navigator.clipboard.writeText(p).then(function(){ alert('已生成并复制到剪贴板：'+p); }); }
    else { alert('已生成新密码（请手动复制）：'+p); }
    document.getElementById('resetPwdTip').classList.remove('is-hidden');
}
function submitResetPwd(){
    if(!resetPwdUsername) return;
    var pwd=document.getElementById('resetPwdNew').value.trim();
    if(!pwd){ alert('请输入新密码'); return; }
    fetch('/admin/users/reset-password', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ username: resetPwdUsername, new_password: pwd })}).then(r=>r.json()).then(d=>{ alert(d.error||'密码已重置'); if(!d.error) { document.getElementById('resetPwdModal').classList.add('is-hidden'); loadUsers(); } });
}
function addUser(e){ e.preventDefault();
    var role=document.getElementById('newRole').value;
    var payload={ username: document.getElementById('newUsername').value, password: document.getElementById('newPassword').value, role: role };
    if(role==='user'){
        payload.allowed_modules=collectNewUserModules();
        var scopes=collectNewUserScopes();
        if(scopes.length) payload.allowed_scopes=scopes;
    }
    fetch('/admin/users/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload)}).then(r=>r.json()).then(d=>{ alert(d.error||'添加成功'); if(!d.error) { loadUsers(); document.getElementById('addUserForm').classList.add('is-hidden'); } });
    return false;
}
var editingUsername = null;
function syncEditRolePanels(){
    var role = (document.getElementById('editRole')||{}).value || 'user';
    var panels = document.getElementById('editPermPanels');
    if (panels) panels.style.display = role === 'user' ? '' : 'none';
}
function editUser(name){
    editingUsername=name;
    fetch('/admin/users/get/'+encodeURIComponent(name)).then(r=>r.json()).then(d=>{
        var u = (d && (d.user || (d.data && d.data.user))) || d.user;
        if(!u){ alert((d && d.error) || '用户不存在'); return; }
        document.getElementById('editUserName').textContent=u.username;
        var roleEl = document.getElementById('editRole');
        if (roleEl) roleEl.value = u.role || 'user';
        document.getElementById('editAllModules').checked = u.allowed_modules&&u.allowed_modules.indexOf('*')>=0;
        MODULE_IDS.forEach(function(id){
            var cb=document.querySelector('#editModulesList input[value="'+id+'"]');
            if(cb) cb.checked = u.allowed_modules&&(u.allowed_modules.indexOf('*')>=0||u.allowed_modules.indexOf(id)>=0);
        });
        var scopes = u.allowed_scopes||[];
        document.querySelectorAll('#editScopesList .edit-scope-cb').forEach(function(cb){
            cb.checked = scopes.indexOf(cb.value) >= 0;
        });
        document.getElementById('editDisabled').checked=!!u.disabled;
        syncEditRolePanels();
        document.getElementById('editUserModal').classList.remove('is-hidden');
    });
}
document.getElementById('editRole').onchange = syncEditRolePanels;
document.getElementById('editAllModules').onchange=function(){
    document.querySelectorAll('#editModulesList input').forEach(function(cb){ cb.checked=this.checked; }.bind(this));
};
function saveEditUser(){
    if(!editingUsername) return;
    var role = (document.getElementById('editRole')||{}).value || 'user';
    var allCb = document.getElementById('editAllModules');
    var listCbs = document.querySelectorAll('#editModulesList input');
    var allowed = role === 'user'
      ? (allCb.checked ? ['*'] : Array.from(listCbs).filter(function(c){ return c.checked; }).map(function(c){ return c.value; }))
      : ['*'];
    var disabled = document.getElementById('editDisabled').checked;
    var scopes = role === 'user'
      ? Array.from(document.querySelectorAll('#editScopesList .edit-scope-cb:checked')).map(function(c){ return c.value; })
      : [];
    fetch('/admin/users/update', {
      method:'POST',
      headers:{'Content-Type':'application/json'},
      body: JSON.stringify({ username: editingUsername, role: role, allowed_modules: allowed, allowed_scopes: scopes, disabled: disabled })
    }).then(r=>r.json()).then(d=>{
      var err = d.error || (d.ok === false ? (d.message || '保存失败') : '');
      alert(err || '已保存');
      if(!err) { loadUsers(); document.getElementById('editUserModal').classList.add('is-hidden'); }
    });
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
    var html = '';
    MODULE_GROUPS.forEach(function(group){
      var ids = (group.ids || []).filter(function(id){ return MODULE_IDS.indexOf(id) >= 0; });
      if (!ids.length) return;
      html += '<div class="perm-module-group"><strong>'+group.title+'</strong><div class="perm-module-group-items">';
      ids.forEach(function(id){
        html += '<label class="perm-check"><input type="checkbox" value="'+id+'" class="edit-mod-cb"> <span>'+(MODULE_NAMES[id]||id)+'</span></label>';
      });
      html += '</div></div>';
    });
    var grouped = {};
    MODULE_GROUPS.forEach(function(g){ (g.ids||[]).forEach(function(id){ grouped[id]=1; }); });
    var orphan = MODULE_IDS.filter(function(id){ return !grouped[id]; });
    if (orphan.length) {
      html += '<div class="perm-module-group"><strong>其他</strong><div class="perm-module-group-items">';
      orphan.forEach(function(id){
        html += '<label class="perm-check"><input type="checkbox" value="'+id+'" class="edit-mod-cb"> <span>'+(MODULE_NAMES[id]||id)+'</span></label>';
      });
      html += '</div></div>';
    }
    list.innerHTML = html;
    document.querySelectorAll('#editModulesList input').forEach(function(cb){
        cb.addEventListener('change', function(){ if(!this.checked) document.getElementById('editAllModules').checked=false; });
    });
    var scopesWrap = document.getElementById('editScopesList');
    SCOPE_IDS.forEach(function(id){
        var label=document.createElement('label');
        label.className='perm-check perm-check--scope';
        label.innerHTML='<input type="checkbox" value="'+id+'" class="edit-scope-cb"> <span><b>'+(SCOPE_NAMES[id]||id)+'</b><em>'+(SCOPE_HINTS[id]||'')+'</em></span>';
        scopesWrap.appendChild(label);
    });
})();
loadUsers();
</script>
<style>
.studio-hint{margin:.25rem 0 0;font-size:12px;color:#667085;line-height:1.45}
.perm-module-grid{display:flex;flex-direction:column;gap:12px}
.perm-module-group{border:1px solid #e5eaf3;border-radius:10px;padding:10px 12px;background:#fafbfc}
.perm-module-group>strong{display:block;margin-bottom:8px;font-size:12px;color:#475467}
.perm-module-group-items{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:6px 12px}
.perm-check{display:flex;align-items:flex-start;gap:8px;font-size:13px;color:#1f2a37;cursor:pointer}
.perm-check input{margin-top:2px}
.perm-scope-list{display:flex;flex-direction:column;gap:8px;margin-top:8px}
.perm-check--scope span{display:flex;flex-direction:column;gap:2px}
.perm-check--scope b{font-weight:600}
.perm-check--scope em{font-style:normal;font-size:12px;color:#667085}
@media(max-width:720px){.perm-module-group-items{grid-template-columns:1fr}}
.pm-table-actions{display:flex;flex-wrap:wrap;align-items:center;gap:6px}
.pm-row-more{position:relative}
.pm-row-more>summary{list-style:none;cursor:pointer;font-size:12px;font-weight:600;color:#475467;padding:6px 10px;border:1px solid #dce4f2;border-radius:6px;background:#fff}
.pm-row-more>summary::-webkit-details-marker{display:none}
.pm-row-more-menu{position:absolute;right:0;top:calc(100% + 4px);z-index:20;min-width:140px;padding:8px;border:1px solid #e5eaf3;border-radius:8px;background:#fff;box-shadow:0 8px 20px rgba(16,24,40,.12);display:flex;flex-direction:column;gap:6px}
</style>
'''


def render_users_page(password_min: int) -> str:
    import json

    from flask import session

    from services.authz import ADMIN_MODULES

    module_ids = json.dumps([m[0] for m in ADMIN_MODULES if m[0] != "user_management"])
    module_names = json.dumps(
        dict((m[0], m[1]) for m in ADMIN_MODULES if m[0] != "user_management")
    )
    current_user = json.dumps(str(session.get("user") or ""))
    return (
        USERS_PAGE.replace("{{PASSWORD_MIN}}", str(password_min))
        .replace("{{MODULE_IDS}}", module_ids)
        .replace("{{MODULE_NAMES}}", module_names)
        .replace("{{CURRENT_USER}}", current_user)
    )
