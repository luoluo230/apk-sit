
var allProjectsCache = [];
var newParticipants = [];
var editParticipants = [];
var _participantCtx = '';
var _pendingParticipantUser = '';
var ROLES = ["\u7b56\u5212", "\u6570\u503c", "\u7f8e\u672f", "\u7279\u6548", "\u524d\u7aef", "\u540e\u7aef", "\u6d4b\u8bd5", "\u5176\u4ed6"];
var _channelsCache = [];
var ALL_CHANNELS = [{"id": "1001", "name": "\u5fae\u4fe1"}, {"id": "1002", "name": "\u6296\u97f3"}];
function parseUserList(str){ return (str||'').split(/[,，\s]+/).map(function(s){ return s.trim(); }).filter(Boolean); }
function openPathPicker(inputId, mode, btnEl){
    var el=document.getElementById(inputId);
    var start=(el&&el.value)?String(el.value).trim():'';
    var btn=btnEl||null;
    var oldText=btn?btn.textContent:'';
    if(btn){ btn.disabled=true; btn.textContent='选择中…'; }
    fetch('/admin/fs/native-pick', {
        method:'POST',
        headers:{'Content-Type':'application/json'},
        credentials:'same-origin',
        body: JSON.stringify({ mode:(mode==='file')?'file':'dir', initial_path:start })
    }).then(function(r){ return r.json(); }).then(function(d){
        if(d.ok&&d.path&&el){ el.value=d.path; return; }
        if(d.cancelled) return;
        alert(d.error||'未能选择路径');
    }).catch(function(){ alert('调用系统选择框失败'); }).finally(function(){
        if(btn){ btn.disabled=false; btn.textContent=oldText||'浏览'; }
    });
}
function _projectBuildPayload(prefix){
    var branchesText = (document.getElementById(prefix+'GitBranches')||{}).value || '';
    var gitBranches = branchesText ? branchesText.split(/\n/).map(function(s){ return s.trim(); }).filter(Boolean) : [];
    var o = {
        app_name: ((document.getElementById(prefix+'AppName')||{}).value||'').trim(),
        git_url: ((document.getElementById(prefix+'GitUrl')||{}).value||'').trim(),
        git_ssh_key_path: ((document.getElementById(prefix+'GitSshKey')||{}).value||'').trim(),
        git_workspace: ((document.getElementById(prefix+'GitWorkspace')||{}).value||'').trim(),
        default_git_branch: ((document.getElementById(prefix+'DefaultGitBranch')||{}).value||'').trim(),
        unity_project_path: ((document.getElementById(prefix+'UnityProjectPath')||{}).value||'').trim(),
        output_base_dir: ((document.getElementById(prefix+'OutputBaseDir')||{}).value||'').trim()
    };
    if(gitBranches.length) o.git_branches = gitBranches;
    return o;
}
function validateProjectGit(prefix, resultId){
    var bp = _projectBuildPayload(prefix);
    var el = document.getElementById(resultId);
    if(el){ el.textContent='验证中…'; el.className='text-xs text-gray-500'; }
    fetch('/api/jenkins-manage/validate-git', { method:'POST', headers:{'Content-Type':'application/json'}, credentials:'same-origin', body: JSON.stringify({ git_url: bp.git_url, git_workspace: bp.git_workspace, git_ssh_key_path: bp.git_ssh_key_path }) })
    .then(function(r){ return r.json(); }).then(function(d){
        if(!el) return;
        if(d.ok){ el.textContent='Git 配置有效'; el.className='text-xs text-green-600'; }
        else{ el.textContent=(d.errors&&d.errors.length)?d.errors.join('；'):'配置有误'; el.className='text-xs text-red-600'; }
    }).catch(function(){ if(el){ el.textContent='验证请求失败'; el.className='text-xs text-red-600'; } });
}
function _fillProjectBuildFields(prefix, p){
    var bc = p.build_config || p || {};
    var setVal = function(id, v){ var el=document.getElementById(id); if(el) el.value = v || ''; };
    setVal(prefix+'AppName', bc.app_name || p.app_name);
    setVal(prefix+'OutputBaseDir', bc.output_base_dir || p.output_base_dir);
    setVal(prefix+'GitUrl', bc.git_url || p.git_url);
    setVal(prefix+'GitWorkspace', bc.git_workspace || p.git_workspace);
    setVal(prefix+'GitSshKey', bc.git_ssh_key_path || p.git_ssh_key_path);
    setVal(prefix+'DefaultGitBranch', bc.default_git_branch || p.default_git_branch);
    setVal(prefix+'UnityProjectPath', bc.unity_project_path || p.unity_project_path);
    var branches = bc.git_branches || p.git_branches || [];
    setVal(prefix+'GitBranches', Array.isArray(branches) ? branches.join('\n') : String(branches||''));
}
var _newGitBtn = document.getElementById('newProjectValidateGitBtn'); if(_newGitBtn) _newGitBtn.onclick=function(){ validateProjectGit('newProject', 'newProjectGitValidateResult'); };
var _editGitBtn = document.getElementById('editProjectValidateGitBtn'); if(_editGitBtn) _editGitBtn.onclick=function(){ validateProjectGit('editProject', 'editProjectGitValidateResult'); };
function renderNewParticipants(){ var ul=document.getElementById('newParticipantsList'); if(!ul) return; ul.innerHTML=newParticipants.map(function(p){ return '<li class="flex justify-between items-center py-1"><span>'+p.user+' <span class="text-gray-500">('+p.role+')</span></span><span><button type="button" onclick="editParticipantRole(\'new\','+JSON.stringify(p.user).replace(/</g,'\u003c')+')" class="text-blue-600 text-xs mr-1">编辑</button><button type="button" onclick="removeParticipant(\'new\','+JSON.stringify(p.user).replace(/</g,'\u003c')+')" class="text-red-600 text-xs">删除</button></span></li>'; }).join('') || '<li class="text-gray-400 text-xs">暂无参与人员</li>'; }
function renderEditParticipants(){ var ul=document.getElementById('editParticipantsList'); if(!ul) return; ul.innerHTML=editParticipants.map(function(p){ return '<li class="flex justify-between items-center py-1"><span>'+p.user+' <span class="text-gray-500">('+p.role+')</span></span><span><button type="button" onclick="editParticipantRole(\'edit\','+JSON.stringify(p.user).replace(/</g,'\u003c')+')" class="text-blue-600 text-xs mr-1">编辑</button><button type="button" onclick="removeParticipant(\'edit\','+JSON.stringify(p.user).replace(/</g,'\u003c')+')" class="text-red-600 text-xs">删除</button></span></li>'; }).join('') || '<li class="text-gray-400 text-xs">暂无参与人员</li>'; }
function addNewParticipant(){ var u=(document.getElementById('newParticipantUser')||{}).value.trim(); if(!u){ alert('请输入用户名'); return; } fetch('/admin/projects/validate-username?username='+encodeURIComponent(u)).then(r=>r.json()).then(function(d){ if(!d.exists){ alert('用户不存在或已禁用'); return; } if(newParticipants.some(function(p){ return p.user===u; })){ alert('已添加过'); return; } _participantCtx='new'; _pendingParticipantUser=u; document.getElementById('roleModalUsername').textContent=u; document.getElementById('roleModalRole').value='其他'; document.getElementById('participantRoleModal').classList.remove('hidden'); }); }
function addEditParticipant(){ var u=(document.getElementById('editParticipantUser')||{}).value.trim(); if(!u){ alert('请输入用户名'); return; } fetch('/admin/projects/validate-username?username='+encodeURIComponent(u)).then(r=>r.json()).then(function(d){ if(!d.exists){ alert('用户不存在或已禁用'); return; } if(editParticipants.some(function(p){ return p.user===u; })){ alert('已添加过'); return; } _participantCtx='edit'; _pendingParticipantUser=u; document.getElementById('roleModalUsername').textContent=u; document.getElementById('roleModalRole').value='其他'; document.getElementById('participantRoleModal').classList.remove('hidden'); }); }
function confirmParticipantRole(){ var r=(document.getElementById('roleModalRole')||{}).value||'其他'; var arr=_participantCtx==='new'?newParticipants:editParticipants; var exists=arr.find(function(x){ return x.user===_pendingParticipantUser; }); if(exists){ exists.role=r; } else { arr.push({user:_pendingParticipantUser,role:r}); if(_participantCtx==='new') document.getElementById('newParticipantUser').value=''; else document.getElementById('editParticipantUser').value=''; } if(_participantCtx==='new') renderNewParticipants(); else renderEditParticipants(); document.getElementById('participantRoleModal').classList.add('hidden'); }
function editParticipantRole(ctx, user){ var arr=ctx==='new'?newParticipants:editParticipants; var p=arr.find(function(x){ return x.user===user; }); if(!p) return; _participantCtx=ctx; _pendingParticipantUser=user; document.getElementById('roleModalUsername').textContent=user; document.getElementById('roleModalRole').value=p.role; document.getElementById('participantRoleModal').classList.remove('hidden'); }
function removeParticipant(ctx, user){ if(ctx==='new'){ newParticipants=newParticipants.filter(function(p){ return p.user!==user; }); renderNewParticipants(); } else { editParticipants=editParticipants.filter(function(p){ return p.user!==user; }); renderEditParticipants(); } }
function setAddFeedback(msg, isError){
    var el = document.getElementById('addProjectFeedback');
    if(!el) return;
    el.textContent = msg || '';
    el.className = 'min-h-[2rem] text-sm font-medium py-1 ' + (isError ? 'text-red-600' : 'text-green-600');
    if(msg) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}
function addProject(){
    var btn = document.getElementById('addProjectBtn');
    try {
        if(btn){ btn.disabled=true; btn.textContent='提交中…'; }
        setAddFeedback('提交中…', false);
        var viewers = parseUserList((document.getElementById('newProjectViewers')||{}).value);
        var phaseEl = document.getElementById('newProjectPhase'); var phase = phaseEl ? phaseEl.value : 'kickoff';
        var editors = newParticipants.map(function(p){ return p.user; });
        var member_roles = {}; newParticipants.forEach(function(p){ member_roles[p.user]=p.role||'其他'; });
        var payload = { id: (document.getElementById('newProjectId')||{}).value.trim(), name: (document.getElementById('newProjectName')||{}).value.trim(), name_en: (document.getElementById('newProjectNameEn')||{}).value.trim(), phase: phase, icon: (document.getElementById('newProjectIcon')||{}).value.trim(), intro: (document.getElementById('newProjectIntro')||{}).value.trim(), detail: (document.getElementById('newProjectDetail')||{}).value.trim(), network_connection: (document.getElementById('newProjectNetwork')||{}).value.trim(), player_public_url: (document.getElementById('newProjectPlayerPublicUrl')||{}).value.trim(), forum_public_url: (document.getElementById('newProjectForumPublicUrl')||{}).value.trim(), admin_public_url: (document.getElementById('newProjectAdminPublicUrl')||{}).value.trim(), viewers: viewers, editors: editors, member_roles: member_roles, game_id: (document.getElementById('newProjectGameId')||{}).value.trim(), game_key: (document.getElementById('newProjectGameKey')||{}).value.trim() };
        Object.assign(payload, _projectBuildPayload('newProject'));
        if(!payload.id||!payload.name){ setAddFeedback('请填写项目ID和名称', true); if(btn){ btn.disabled=false; btn.textContent='添加项目'; } return; }
        if(!payload.game_id || !payload.game_key){ setAddFeedback('请先点击“系统生成凭据”', true); if(btn){ btn.disabled=false; btn.textContent='添加项目'; } return; }
        fetch('/admin/projects/create', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' })
        .then(function(r){ var ct = r.headers.get('Content-Type')||''; return r.text().then(function(t){ var d; try{ d = (ct.indexOf('json')>=0 && t) ? JSON.parse(t) : {}; } catch(e){ d = { error: t && t.length<200 ? t : (r.status===403 ? '无权限或未登录' : r.status===302 ? '请先登录' : '请求异常') }; } return { ok: r.ok, status: r.status, data: d }; }); })
        .then(function(res){ if(btn){ btn.disabled=false; btn.textContent='添加项目'; } var d=res.data; if(!res.ok || d.error){ setAddFeedback(d.error||'添加失败（'+res.status+'）', true); return; } setAddFeedback('添加成功，已刷新列表', false); loadProjects(); setTimeout(function(){ var f=document.getElementById('addProjectForm'); if(f) f.classList.add('hidden'); setAddFeedback('', false); }, 1500); })
        .catch(function(err){ if(btn){ btn.disabled=false; btn.textContent='添加项目'; } setAddFeedback('网络错误或请求失败: '+(err.message||''), true); });
    } catch(e) {
        if(btn){ btn.disabled=false; btn.textContent='添加项目'; }
        setAddFeedback('错误: ' + (e.message || String(e)), true);
    }
}
function generateProjectCredentials(){
    var pid = (document.getElementById('newProjectId')||{}).value.trim() || 'project';
    fetch('/admin/projects/generate-credentials', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({ id: pid }), credentials:'same-origin' })
    .then(function(r){ return r.json(); })
    .then(function(d){
        if(d.error){ alert(d.error); return; }
        document.getElementById('newProjectGameId').value = d.game_id || '';
        document.getElementById('newProjectGameKey').value = d.game_key || '';
    })
    .catch(function(){ alert('生成凭据失败'); });
}
function uploadProjectIcon(fileInput, hiddenId, previewId, callback){
    if(!fileInput||!fileInput.files||!fileInput.files[0]) return;
    var fd=new FormData(); fd.append('icon', fileInput.files[0]);
    fetch('/admin/projects/upload-icon', { method:'POST', body: fd, credentials:'same-origin' }).then(r=>r.json()).then(function(d){ if(d.url){ var h=document.getElementById(hiddenId); if(h) h.value=d.url; var el=document.getElementById(previewId); if(el) el.innerHTML='<img src="'+d.url+'" alt="" class="h-10 w-10 rounded object-cover">'; if(callback) callback(d.url); } else alert(d.error||'上传失败'); });
}
var _el = document.getElementById('newProjectIconFile'); if(_el) _el.onchange=function(){ uploadProjectIcon(this, 'newProjectIcon', 'newProjectIconPreview'); };
_el = document.getElementById('editProjectIconFile'); if(_el) _el.onchange=function(){ uploadProjectIcon(this, 'editProjectIcon', 'editProjectIconPreview'); };
function renderProjectsTable(projects){
    var q=(document.getElementById('projectSearch')||{}).value||''; q=q.trim().toLowerCase();
    var list = q ? projects.filter(function(p){ return (p.id||'').toLowerCase().indexOf(q)>=0 || (p.name||'').toLowerCase().indexOf(q)>=0 || (p.name_en||'').toLowerCase().indexOf(q)>=0; }) : projects;
    var t=document.getElementById('projectsTable');
    t.innerHTML = list.map(function(p, i){
        var rowClass = (i%2===0) ? 'bg-white' : 'bg-slate-50/60';
        var iconHtml = p.icon ? '<img src="'+p.icon+'" alt="" class="w-8 h-8 rounded-lg object-cover ring-1 ring-slate-200/80" onerror="this.style.display=\'none\'">' : '<span class="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-slate-100 text-slate-400 text-xs"><i class="fas fa-folder"></i></span>';
        var phaseLabel = p.phase_label || p.phase || '-';
        var introSnip = (p.intro||'').slice(0,20); if((p.intro||'').length>20) introSnip+='…';
        var dateStr = (p.created_at||'').slice(0,19).replace('T',' ') || '-';
        var canEdit = p.can_edit;
        var statusBadge = (p.status==='archived') ? ' <span class="px-2 py-0.5 rounded text-xs bg-gray-200 text-gray-600">已归档</span>' : ((p.is_template) ? ' <span class="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">模板</span>' : '');
        var archiveBtn = canEdit && p.status!=='archived'
            ? '<button onclick="archiveProject(\''+p.id+'\', true)" class="inline-flex items-center whitespace-nowrap px-2.5 py-1 text-xs text-slate-600 bg-slate-50 hover:bg-slate-100 rounded-lg">归档</button>'
            : (canEdit && p.status==='archived'
                ? '<button onclick="archiveProject(\''+p.id+'\', false)" class="inline-flex items-center whitespace-nowrap px-2.5 py-1 text-xs text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg">取消归档</button>'
                : '');
        var actions = '<a href="/admin/projects/'+p.id+'" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded">项目中心</a>'
            + '<a href="/admin/projects/'+p.id+'/tasks" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded">任务</a>'
            + '<a href="/admin/projects/'+p.id+'/versions" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded">版本</a>';
        if(canEdit){
            actions += '<button onclick="editProject(\''+p.id+'\')" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-blue-700 bg-blue-50 hover:bg-blue-100 rounded">编辑</button>';
            actions += '<button onclick="deleteProject(\''+p.id+'\')" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-red-700 bg-red-50 hover:bg-red-100 rounded">删除</button>';
        } else {
            actions += '<span class="text-slate-400 text-xs whitespace-nowrap">仅查看</span>';
        }
        return '<tr class="'+rowClass+' hover:bg-indigo-50/40"><td class="px-6 py-2.5 align-middle">'+iconHtml+'</td><td class="px-6 py-2.5 align-middle font-medium text-slate-900 whitespace-nowrap">'+p.id+'</td><td class="px-6 py-2.5 align-middle text-slate-800">'+p.name+statusBadge+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500">'+(p.name_en||'-')+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500 whitespace-nowrap">'+phaseLabel+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500 max-w-[140px] truncate" title="'+((p.intro||'')+'').replace(/"/g,'&quot;')+'">'+introSnip+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500">'+(p.created_by||'-')+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-500 whitespace-nowrap">'+dateStr+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-600">'+(p.task_count||0)+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-600">'+p.apk_count+'</td><td class="px-6 py-2.5 align-middle text-xs text-slate-600">'+(p.download_count||0)+'</td><td class="px-6 py-2.5 align-middle min-w-[280px]"><div class="flex items-center gap-1.5 flex-nowrap overflow-x-auto">'+actions+'</div></td></tr>';
    }).join('');
}
function openChannelManageModal(){
    document.getElementById('channelManageModal').classList.remove('hidden');
    loadChannels();
}
function closeChannelManageModal(){
    document.getElementById('channelManageModal').classList.add('hidden');
}
function resetChannelForm(){
    document.getElementById('channelFormEditingId').value='';
    document.getElementById('channelFormId').disabled=false;
    document.getElementById('channelFormId').value='';
    document.getElementById('channelFormName').value='';
    document.getElementById('channelFormOrder').value='0';
    document.getElementById('channelFormDesc').value='';
    var apkEl=document.getElementById('channelFormApkSubdir'); if(apkEl) apkEl.value='';
    var bpEl=document.getElementById('channelFormBuildParam'); if(bpEl) bpEl.value='';
}
function fillChannelForm(ch){
    document.getElementById('channelFormEditingId').value = ch.id || '';
    var idEl = document.getElementById('channelFormId');
    idEl.value = ch.id || '';
    idEl.disabled = true;
    document.getElementById('channelFormName').value = ch.name || '';
    document.getElementById('channelFormOrder').value = (ch.order!=null ? ch.order : 0);
    document.getElementById('channelFormDesc').value = ch.description || '';
    var apkEl=document.getElementById('channelFormApkSubdir'); if(apkEl) apkEl.value=ch.apk_subdir||'';
    var bpEl=document.getElementById('channelFormBuildParam'); if(bpEl) bpEl.value=ch.build_param||'';
}
function renderChannelTable(){
    var tbody = document.getElementById('channelTableBody');
    var empty = document.getElementById('channelEmptyTip');
    if(!tbody) return;
    if(!_channelsCache || !_channelsCache.length){
        tbody.innerHTML = '';
        if(empty) empty.classList.remove('hidden');
        return;
    }
    if(empty) empty.classList.add('hidden');
    tbody.innerHTML = _channelsCache.map(function(ch){
        var subdir = (ch.apk_subdir||'').slice(0,12);
        var bp = (ch.build_param||'').slice(0,20);
        var badge = '<span class="inline-flex items-center px-2 py-0.5 rounded-full bg-slate-100 text-slate-600 text-[10px]">'+(ch.id||'')+'</span>';
        var chId = (ch.id||'').replace(/&/g,'&amp;').replace(/"/g,'&quot;').replace(/</g,'&lt;');
        return '<tr>'
            + '<td class="py-1.5 pr-2">'+badge+'</td>'
            + '<td class="py-1.5 pr-2">'+(ch.name||'-')+'</td>'
            + '<td class="py-1.5 pr-2 text-slate-500">'+(subdir||'-')+'</td>'
            + '<td class="py-1.5 pr-2 text-slate-500">'+(bp||'-')+'</td>'
            + '<td class="py-1.5 space-x-1">'
            +   '<button type="button" class="channel-edit-btn px-2 py-0.5 text-[11px] text-blue-700 bg-blue-50 hover:bg-blue-100 rounded" data-channel-id="'+chId+'">编辑</button>'
            +   '<button type="button" class="channel-delete-btn px-2 py-0.5 text-[11px] text-red-700 bg-red-50 hover:bg-red-100 rounded" data-channel-id="'+chId+'">删除</button>'
            + '</td>'
            + '</tr>';
    }).join('');
}
function loadChannels(){
    fetch('/admin/channels', { credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){
        _channelsCache = d.channels || [];
        renderChannelTable();
    }).catch(function(){
        _channelsCache = [];
        renderChannelTable();
    });
}
function submitChannelForm(){
    var editingId = document.getElementById('channelFormEditingId').value || '';
    var id = document.getElementById('channelFormId').value.trim();
    var name = document.getElementById('channelFormName').value.trim();
    var order = document.getElementById('channelFormOrder').value;
    var desc = document.getElementById('channelFormDesc').value.trim();
    var apkSubdir = (document.getElementById('channelFormApkSubdir')||{}).value.trim();
    var buildParam = (document.getElementById('channelFormBuildParam')||{}).value.trim();
    if(!id || !name){
        alert('请填写渠道 ID 和名称');
        return;
    }
    var payload = { id: id, name: name, order: order, description: desc, apk_subdir: apkSubdir, build_param: buildParam };
    var url = editingId ? '/admin/channels/update' : '/admin/channels/create';
    fetch(url, { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload), credentials:'same-origin' }).then(function(r){ return r.json(); }).then(function(d){
        if(d.error){
            alert(d.error);
            return;
        }
        resetChannelForm();
        loadChannels();
    });
}
document.addEventListener('click', function(e){
    var editBtn = e.target.closest('.channel-edit-btn');
    if(editBtn){ var id = editBtn.getAttribute('data-channel-id'); if(id && _channelsCache){ var ch = _channelsCache.find(function(c){ return (c.id||'')===id; }); if(ch) fillChannelForm(ch); } return; }
    var delBtn = e.target.closest('.channel-delete-btn');
    if(delBtn){ var id = delBtn.getAttribute('data-channel-id'); if(id) deleteChannel(id); }
}, true);
function deleteChannel(id){
    if(!id) return;
    if(!confirm('确定删除渠道 '+id+'？若已有版本使用该渠道，将无法删除。')) return;
    fetch('/admin/channels/delete/'+encodeURIComponent(id), { method:'DELETE', credentials:'same-origin' }).then(function(r){
        var ct = (r.headers.get('Content-Type')||'').toLowerCase();
        if(ct.indexOf('application/json')<0) throw new Error('需要重新登录');
        return r.text();
    }).then(function(text){
        try{ return JSON.parse(text||'{}'); } catch(e){ throw new Error('解析失败，请刷新重试'); }
    }).then(function(d){
        if(d.error){ alert(d.error); return; }
        loadChannels();
    }).catch(function(e){ alert(e.message||'删除失败，请刷新重试'); });
}
function loadProjects(){
    var statusFilter = (document.getElementById('projectStatusFilter')||{}).value || 'active';
    fetch('/admin/projects/list?status='+encodeURIComponent(statusFilter), { credentials: 'same-origin' }).then(function(r){
        if(!r.ok) throw new Error(''+r.status);
        var ct = (r.headers.get('Content-Type')||'').toLowerCase();
        if(ct.indexOf('application/json')<0) throw new Error('需要重新登录');
        return r.text();
    }).then(function(text){
        try{ return JSON.parse(text); } catch(e){ throw new Error('解析失败，请刷新或重新登录'); }
    }).then(function(d){ allProjectsCache = d.projects||[]; renderProjectsTable(allProjectsCache); }).catch(function(e){ allProjectsCache = []; var t = document.getElementById('projectsTable'); if(t) t.innerHTML = '<tr><td colspan="12" class="px-6 py-8 text-center text-red-500">加载失败（'+ (e.message||'请刷新或重新登录') +'）</td></tr>'; });
}
function editProject(id){
    fetch('/admin/projects/get/'+encodeURIComponent(id)).then(r=>r.json()).then(d=>{
        if(d.error){ alert(d.error); return; }
        var p=d.project;
        document.getElementById('editProjectIdLabel').textContent=id;
        document.getElementById('editProjectName').value=p.name||'';
        document.getElementById('editProjectNameEn').value=p.name_en||'';
        var phaseSel=document.getElementById('editProjectPhase'); if(phaseSel) phaseSel.value=p.phase||'kickoff';
        document.getElementById('editProjectIcon').value=p.icon||'';
        editParticipants=(p.editors||[]).map(function(u){ return {user:u, role:(p.member_roles||{})[u]||'其他'}; }); renderEditParticipants();
        document.getElementById('editProjectViewers').value=(p.viewers||[]).join(', ');
        var projChans = p.channels||[];
        var chWrap = document.getElementById('editProjectChannels');
        if(chWrap && ALL_CHANNELS){
            chWrap.innerHTML = ALL_CHANNELS.map(function(c){ return '<label class="flex items-center gap-1.5"><input type="checkbox" class="edit-channel-cb" value="'+c.id+'" '+(projChans.indexOf(c.id)>=0?'checked':'')+'><span>'+c.name+'</span></label>'; }).join('');
        }
        document.getElementById('editProjectIntro').value=p.intro||'';
        document.getElementById('editProjectDetail').value=p.detail||'';
        document.getElementById('editProjectNetwork').value=p.network_connection||'';
        _fillProjectBuildFields('editProject', p);
        var playerUrlEl = document.getElementById('editProjectPlayerPublicUrl'); if(playerUrlEl) playerUrlEl.value=p.player_public_url||'';
        var forumUrlEl = document.getElementById('editProjectForumPublicUrl'); if(forumUrlEl) forumUrlEl.value=p.forum_public_url||'';
        var adminUrlEl = document.getElementById('editProjectAdminPublicUrl'); if(adminUrlEl) adminUrlEl.value=p.admin_public_url||'';
        var prev=document.getElementById('editProjectIconPreview'); prev.innerHTML=p.icon ? '<img src="'+p.icon+'" alt="" class="h-10 w-10 rounded object-cover">' : '';
        document.getElementById('editProjectIconFile').value='';
        document.getElementById('editProjectModal').classList.remove('hidden');
    });
}
function saveEditProject(){
    var id = document.getElementById('editProjectIdLabel').textContent;
    var viewers = parseUserList(document.getElementById('editProjectViewers').value);
    var editors = editParticipants.map(function(p){ return p.user; });
    var member_roles = {}; editParticipants.forEach(function(p){ member_roles[p.user]=p.role||'其他'; });
    var phaseEl = document.getElementById('editProjectPhase'); var phase = phaseEl ? phaseEl.value : 'kickoff';
    var channels = []; document.querySelectorAll('.edit-channel-cb:checked').forEach(function(cb){ channels.push(cb.value); });
    var payload = { id: id, name: document.getElementById('editProjectName').value.trim(), name_en: document.getElementById('editProjectNameEn').value.trim(), phase: phase, icon: document.getElementById('editProjectIcon').value.trim(), intro: document.getElementById('editProjectIntro').value.trim(), detail: document.getElementById('editProjectDetail').value.trim(), network_connection: document.getElementById('editProjectNetwork').value.trim(), player_public_url: (document.getElementById('editProjectPlayerPublicUrl')||{}).value.trim(), forum_public_url: (document.getElementById('editProjectForumPublicUrl')||{}).value.trim(), admin_public_url: (document.getElementById('editProjectAdminPublicUrl')||{}).value.trim(), viewers: viewers, editors: editors, member_roles: member_roles, channels: channels };
    Object.assign(payload, _projectBuildPayload('editProject'));
    fetch('/admin/projects/update', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify(payload) }).then(r=>r.json()).then(d=>{ alert(d.error||'已保存'); if(!d.error) { document.getElementById('editProjectModal').classList.add('hidden'); loadProjects(); } });
}
function archiveProject(id, archive){ fetch('/admin/projects/'+encodeURIComponent(id)+'/archive', { method:'POST', headers:{'Content-Type':'application/json'}, body: JSON.stringify({archive: archive}), credentials:'same-origin' }).then(r=>r.json()).then(d=>{ alert(d.error||(archive?'已归档':'已取消归档')); if(!d.error) loadProjects(); }); }
function deleteProject(id){ if(!confirm('确定删除项目 '+id+'？')) return; fetch('/admin/projects/delete/'+encodeURIComponent(id), { method:'DELETE' }).then(r=>r.json()).then(d=>{ alert(d.error||'已删除'); if(!d.error) loadProjects(); }); }
function ensureProjectDomainFields(){
    var addViewerInput = document.getElementById('newProjectViewers');
    if(addViewerInput && !document.getElementById('newProjectPlayerPublicUrl')){
        var addRow = document.createElement('div');
        addRow.className = 'grid grid-cols-1 md:grid-cols-3 gap-4';
        addRow.innerHTML =
            '<div><label class="block text-xs font-medium text-slate-500 mb-1">玩家官网域名</label><input type="text" id="newProjectPlayerPublicUrl" placeholder="https://game.example.com" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>'
            + '<div><label class="block text-xs font-medium text-slate-500 mb-1">论坛域名</label><input type="text" id="newProjectForumPublicUrl" placeholder="https://forum.example.com" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>'
            + '<div><label class="block text-xs font-medium text-slate-500 mb-1">开发后台域名</label><input type="text" id="newProjectAdminPublicUrl" placeholder="https://studio.example.com" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>';
        var addTargetRow = addViewerInput.closest('div.grid');
        if(addTargetRow && addTargetRow.parentNode){
            addTargetRow.parentNode.insertBefore(addRow, addTargetRow);
        }
    }
    var editViewerInput = document.getElementById('editProjectViewers');
    if(editViewerInput && !document.getElementById('editProjectPlayerPublicUrl')){
        var editRow = document.createElement('div');
        editRow.className = 'grid grid-cols-1 md:grid-cols-3 gap-4';
        editRow.innerHTML =
            '<div><label class="block text-xs font-medium text-gray-500 mb-1">玩家官网域名</label><input type="text" id="editProjectPlayerPublicUrl" placeholder="https://game.example.com" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>'
            + '<div><label class="block text-xs font-medium text-gray-500 mb-1">论坛域名</label><input type="text" id="editProjectForumPublicUrl" placeholder="https://forum.example.com" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>'
            + '<div><label class="block text-xs font-medium text-gray-500 mb-1">开发后台域名</label><input type="text" id="editProjectAdminPublicUrl" placeholder="https://studio.example.com" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>';
        var editTargetRow = editViewerInput.closest('div.grid');
        if(editTargetRow && editTargetRow.parentNode){
            editTargetRow.parentNode.insertBefore(editRow, editTargetRow);
        }
    }
}
ensureProjectDomainFields();
var searchEl = document.getElementById('projectSearch'); if(searchEl) searchEl.oninput = function(){ renderProjectsTable(allProjectsCache); };
loadProjects();



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
    