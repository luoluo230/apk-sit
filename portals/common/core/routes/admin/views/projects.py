# -*- coding: utf-8 -*-
"""Admin projects management page template."""

PROJECTS_PAGE = '''
<section class="space-y-5">
    <div class="flex items-end justify-between gap-2">
        <div>
            <p class="text-[11px] font-semibold text-slate-500 tracking-[0.16em] uppercase">项目中心</p>
            <h2 class="text-xl font-semibold text-slate-900 mt-1">项目列表</h2>
            <p class="text-sm text-slate-500 mt-1">为每个 APK 项目配置成员、阶段与权限，进入项目中心管理任务与版本。</p>
        </div>
        <div class="flex items-center gap-2">
            <select id="projectStatusFilter" onchange="loadProjects()" class="px-3 py-1.5 border border-slate-200 rounded-xl text-sm bg-white shadow-sm">
                <option value="active">仅活跃</option>
                <option value="archived">仅归档</option>
                <option value="">全部</option>
            </select>
            <input type="text" id="projectSearch" placeholder="搜索项目ID、名称、英文名…" class="px-3 py-1.5 border border-slate-200 rounded-xl text-sm w-56 focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500 bg-white shadow-sm">
            <button type="button" onclick="openChannelManageModal()" class="inline-flex items-center px-3.5 py-1.5 rounded-xl border border-slate-200 bg-white text-sm text-slate-700 hover:bg-slate-50 shadow-sm">
                <i class="fas fa-layer-group mr-1.5 text-slate-500"></i> 渠道管理
            </button>
            <button type="button" onclick="var f=document.getElementById('addProjectForm'); if(f.classList.contains('hidden')){ newParticipants=[]; renderNewParticipants(); } f.classList.toggle('hidden')" class="inline-flex items-center px-4 py-2.5 rounded-xl bg-indigo-600 text-white text-sm font-medium shadow-sm hover:bg-indigo-700 transition">
                <i class="fas fa-plus mr-1.5"></i> 添加项目
            </button>
        </div>
    </div>
    <div id="addProjectForm" class="px-6 py-5 border border-slate-200 rounded-2xl bg-white/95 shadow-sm hidden">
        <form onsubmit="return false;" class="space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4">
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目ID（英文）</label><input type="text" id="newProjectId" placeholder="如 MyGame" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" required></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">名称</label><input type="text" id="newProjectName" placeholder="项目名称" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500" required></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">英文名</label><input type="text" id="newProjectNameEn" placeholder="English name" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目图标</label><div class="flex items-center gap-2"><input type="file" id="newProjectIconFile" accept="image/*" class="text-sm"><span id="newProjectIconPreview" class="text-slate-400 text-xs">未上传</span></div><input type="hidden" id="newProjectIcon" value=""></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目阶段</label><select id="newProjectPhase" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500">{{PROJECT_PHASE_OPTIONS}}</select></div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1">gameId（唯一，必填）</label>
                    <input type="text" id="newProjectGameId" readonly class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-slate-50">
                </div>
                <div>
                    <label class="block text-xs font-medium text-slate-500 mb-1">gameKey（唯一，必填）</label>
                    <input type="text" id="newProjectGameKey" readonly class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm bg-slate-50">
                </div>
                <div class="flex items-end">
                    <button type="button" onclick="generateProjectCredentials()" class="w-full px-3 py-1.5 rounded-lg bg-violet-600 text-white text-sm font-medium hover:bg-violet-700">系统生成凭据</button>
                </div>
            </div>
            <div><label class="block text-xs font-medium text-slate-500 mb-1">简介</label><input type="text" id="newProjectIntro" placeholder="简短介绍" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
            <div><label class="block text-xs font-medium text-slate-500 mb-1">详情</label><textarea id="newProjectDetail" rows="2" placeholder="详细描述" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></textarea></div>
            <div><label class="block text-xs font-medium text-slate-500 mb-1">网络连接说明</label><input type="text" id="newProjectNetwork" placeholder="如：需内网/外网" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
            <details class="mt-2 rounded-lg border border-slate-200 p-3" open>
                <summary class="cursor-pointer text-sm font-medium text-slate-700">构建配置（Git / APP / Unity）</summary>
                <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label class="block text-xs font-medium text-slate-500 mb-1">默认 APP_NAME</label><input type="text" id="newProjectAppName" placeholder="如 GameKu" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm"></div>
                    <div><label class="block text-xs font-medium text-slate-500 mb-1">OUTPUT_BASE_DIR（可选）</label><div class="flex gap-2"><input type="text" id="newProjectOutputBaseDir" placeholder="/path/to/output" class="flex-1 min-w-0 px-3 py-1.5 border border-slate-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('newProjectOutputBaseDir','dir',this)" class="px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 bg-white hover:bg-slate-50 shrink-0">浏览</button></div></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-slate-500 mb-1">Git 仓库 URL</label><input type="text" id="newProjectGitUrl" placeholder="https://或 git@" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm"></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-slate-500 mb-1">Git 工作目录</label><div class="flex gap-2"><input type="text" id="newProjectGitWorkspace" placeholder="/path/to/clone" class="flex-1 min-w-0 px-3 py-1.5 border border-slate-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('newProjectGitWorkspace','dir',this)" class="px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 bg-white hover:bg-slate-50 shrink-0">浏览</button></div><p class="text-xs text-slate-400 mt-1">仓库根即 Unity 工程根时，可与下方 Unity 项目路径填相同目录</p></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-slate-500 mb-1">Git SSH 密钥路径（可选）</label><p class="text-xs text-slate-400 mt-0.5 mb-1">本机 Git/SSH 已配置时可留空；Jenkins 构建将使用系统默认 SSH 认证</p><div class="flex gap-2"><input type="text" id="newProjectGitSshKey" placeholder="如 ~/.ssh/id_ed25519" class="flex-1 min-w-0 px-3 py-1.5 border border-slate-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('newProjectGitSshKey','file',this)" class="px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 bg-white hover:bg-slate-50 shrink-0">浏览</button></div></div>
                    <div><label class="block text-xs font-medium text-slate-500 mb-1">默认 Git 分支</label><input type="text" id="newProjectDefaultGitBranch" placeholder="main" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm"></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-slate-500 mb-1">Git 分支列表（每行一个）</label><textarea id="newProjectGitBranches" rows="2" placeholder="main&#10;develop" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-xs"></textarea></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-slate-500 mb-1">Unity 项目路径（可选）</label><div class="flex gap-2"><input type="text" id="newProjectUnityProjectPath" placeholder="/path/to/unity/project" class="flex-1 min-w-0 px-3 py-1.5 border border-slate-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('newProjectUnityProjectPath','dir',this)" class="px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 bg-white hover:bg-slate-50 shrink-0">浏览</button></div></div>
                    <div class="md:col-span-2 flex items-center gap-2"><button type="button" id="newProjectValidateGitBtn" class="px-3 py-1.5 bg-slate-200 rounded text-xs hover:bg-slate-300">验证 Git 配置</button><span id="newProjectGitValidateResult" class="text-xs"></span></div>
                </div>
            </details>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-slate-500 mb-1">可查看用户</label><input type="text" id="newProjectViewers" placeholder="多个用户名用逗号分隔" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500"></div>
                <div><label class="block text-xs font-medium text-slate-500 mb-1">项目参与人员（可编辑）</label><div class="flex gap-2"><input type="text" id="newParticipantUser" placeholder="输入用户名" class="flex-1 px-3 py-1.5 border border-slate-200 rounded-lg text-sm"><button type="button" onclick="addNewParticipant()" class="px-3 py-1.5 bg-indigo-50 text-indigo-700 rounded-lg text-sm">验证并添加</button></div><ul id="newParticipantsList" class="mt-2 space-y-1 text-sm"></ul></div>
            </div>
            <div id="addProjectFeedback" class="min-h-[2rem] text-sm font-medium py-1"></div>
            <div class="flex gap-2 justify-end"><button type="button" onclick="document.getElementById('addProjectForm').classList.add('hidden')" class="px-4 py-2.5 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50">取消</button><button type="button" id="addProjectBtn" onclick="addProject()" class="px-4 py-2.5 bg-emerald-600 text-white text-sm font-medium rounded-lg hover:bg-emerald-700 transition">添加项目</button></div>
        </form>
    </div>
    <div class="bg-white/95 rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">
        <div class="px-5 py-3 border-b border-slate-100 flex items-center justify-between">
            <h3 class="text-sm font-semibold text-slate-900">项目列表</h3>
            <p class="text-xs text-slate-500">包含当前账号可见的所有项目。</p>
        </div>
        <div class="overflow-x-auto">
            <table class="min-w-full xl:min-w-[1360px]">
                <thead class="bg-slate-50/80 border-b border-slate-200/80">
                    <tr>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">图标</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">项目ID</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">名称</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">英文名</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">阶段</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">简介</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">创建者</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">创建时间</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">任务</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">APK</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider">下载量</th>
                        <th class="px-6 py-3.5 text-left text-[11px] font-semibold text-slate-500 uppercase tracking-wider w-[280px]">操作</th>
                    </tr>
                </thead>
                <tbody id="projectsTable" class="divide-y divide-slate-100"></tbody>
            </table>
        </div>
    </div>
</section>
<div id="channelManageModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-xl max-h-[90vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-slate-100 bg-slate-50/80 flex items-center justify-between">
            <div>
                <h3 class="text-sm font-semibold text-slate-900">渠道管理</h3>
                <p class="text-xs text-slate-500 mt-0.5">维护版本渠道（如开发版、测试版、线上版），用于版本管理与下载中心筛选。</p>
            </div>
            <button type="button" onclick="closeChannelManageModal()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>
        </div>
        <div class="px-6 py-4 space-y-4 overflow-y-auto flex-1">
            <div class="border border-dashed border-slate-200 rounded-xl p-3 bg-slate-50/60">
                <div class="grid grid-cols-[1.2fr,1.2fr,0.6fr] gap-3 items-end">
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">渠道 ID</label>
                        <input type="text" id="channelFormId" placeholder="如 dev / test / production" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">渠道名称</label>
                        <input type="text" id="channelFormName" placeholder="如 开发版 / 测试版 / 线上版" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500">
                    </div>
                    <div>
                        <label class="block text-xs font-medium text-slate-600 mb-1">排序</label>
                        <input type="number" id="channelFormOrder" value="0" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500">
                    </div>
                </div>
                <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-2">
                    <div><label class="block text-xs font-medium text-slate-600 mb-1">APK 子目录（可选）</label><input type="text" id="channelFormApkSubdir" placeholder="如 dev、test" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"></div>
                    <div><label class="block text-xs font-medium text-slate-600 mb-1">构建参数（可选）</label><input type="text" id="channelFormBuildParam" placeholder="如 CHANNEL=dev" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"></div>
                </div>
                <div class="mt-3">
                    <label class="block text-xs font-medium text-slate-600 mb-1">说明（可选）</label>
                    <textarea id="channelFormDesc" rows="2" placeholder="用于标记该渠道的用途，例如“内部联调测试”、“线上正式发布”等" class="w-full px-3 py-1.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500/40 focus:border-indigo-500"></textarea>
                </div>
                <div class="mt-3 flex justify-end gap-2">
                    <button type="button" onclick="resetChannelForm()" class="px-3 py-2 text-xs text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50">重置</button>
                    <button type="button" onclick="submitChannelForm()" class="px-4 py-2 text-xs font-medium rounded-lg bg-amber-600 text-white hover:bg-amber-700 shadow-sm">保存渠道</button>
                </div>
                <input type="hidden" id="channelFormEditingId" value="">
            </div>
            <div>
                <h4 class="text-xs font-semibold text-slate-500 mb-2">已有渠道</h4>
                <table class="w-full text-xs">
                    <thead class="border-b border-slate-200 text-slate-500">
                        <tr><th class="py-1.5 text-left">ID</th><th class="py-1.5 text-left">名称</th><th class="py-1.5 text-left">APK 子目录</th><th class="py-1.5 text-left">构建参数</th><th class="py-1.5 text-left w-28">操作</th></tr>
                    </thead>
                    <tbody id="channelTableBody" class="divide-y divide-slate-100"></tbody>
                </table>
                <p id="channelEmptyTip" class="py-4 text-center text-xs text-slate-400 hidden">暂无渠道，可在上方添加，例如 dev / test / production。</p>
            </div>
        </div>
        <div class="px-6 py-3 border-t border-slate-100 bg-slate-50/80 flex justify-end">
            <button type="button" onclick="closeChannelManageModal()" class="px-4 py-1.5 text-sm text-slate-600 bg-white border border-slate-200 rounded-lg hover:bg-slate-50">关闭</button>
        </div>
    </div>
</div>
<div id="participantRoleModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-[60] p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-xl shadow-xl w-80 p-5" onclick="event.stopPropagation()">
        <h4 class="font-semibold text-gray-800 mb-2">设定角色</h4>
        <p class="text-sm text-gray-500 mb-3">用户：<strong id="roleModalUsername"></strong></p>
        <select id="roleModalRole" class="w-full px-3 py-1.5 border rounded-lg text-sm mb-4">{{PROJECT_ROLE_OPTIONS}}</select>
        <div class="flex gap-2"><button type="button" onclick="confirmParticipantRole()" class="flex-1 px-4 py-2 bg-blue-600 text-white rounded-lg text-sm">确认</button><button type="button" onclick="document.getElementById('participantRoleModal').classList.add('hidden')" class="px-4 py-1.5 border rounded-lg text-sm">取消</button></div>
    </div>
</div>
<div id="editProjectModal" class="hidden fixed inset-0 bg-black/60 flex items-center justify-center z-50 p-4" onclick="if(event.target===this) this.classList.add('hidden')">
    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-2xl max-h-[90vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
        <div class="px-6 py-4 border-b border-gray-100 bg-gray-50/80 flex-shrink-0"><h3 class="text-lg font-semibold text-gray-800">编辑项目</h3><p class="text-sm text-gray-500 mt-0.5">项目ID：<strong id="editProjectIdLabel" class="text-gray-800"></strong></p></div>
        <div class="px-6 py-5 overflow-y-auto flex-1 space-y-4">
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-gray-500 mb-1">名称</label><input type="text" id="editProjectName" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
                <div><label class="block text-xs font-medium text-gray-500 mb-1">英文名</label><input type="text" id="editProjectNameEn" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
            </div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">项目阶段</label><select id="editProjectPhase" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500">{{PROJECT_PHASE_OPTIONS}}</select></div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">项目图标</label><div class="flex items-center gap-2 flex-wrap"><input type="file" id="editProjectIconFile" accept="image/*" class="text-sm"><span id="editProjectIconPreview" class="text-gray-500 text-xs"></span></div><input type="hidden" id="editProjectIcon" value=""></div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">简介</label><input type="text" id="editProjectIntro" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">详情</label><textarea id="editProjectDetail" rows="2" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></textarea></div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">网络连接说明</label><input type="text" id="editProjectNetwork" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
            <details class="rounded-lg border border-gray-200 p-3" open>
                <summary class="cursor-pointer text-sm font-medium text-gray-700">构建配置（Git / APP / Unity）</summary>
                <div class="mt-3 grid grid-cols-1 md:grid-cols-2 gap-4">
                    <div><label class="block text-xs font-medium text-gray-500 mb-1">默认 APP_NAME</label><input type="text" id="editProjectAppName" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm"></div>
                    <div><label class="block text-xs font-medium text-gray-500 mb-1">OUTPUT_BASE_DIR（可选）</label><div class="flex gap-2"><input type="text" id="editProjectOutputBaseDir" class="flex-1 min-w-0 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('editProjectOutputBaseDir','dir',this)" class="px-3 py-1.5 border border-gray-200 rounded-lg text-xs text-gray-700 bg-white hover:bg-gray-50 shrink-0">浏览</button></div></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-gray-500 mb-1">Git 仓库 URL</label><input type="text" id="editProjectGitUrl" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm"></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-gray-500 mb-1">Git 工作目录</label><div class="flex gap-2"><input type="text" id="editProjectGitWorkspace" class="flex-1 min-w-0 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('editProjectGitWorkspace','dir',this)" class="px-3 py-1.5 border border-gray-200 rounded-lg text-xs text-gray-700 bg-white hover:bg-gray-50 shrink-0">浏览</button></div><p class="text-xs text-gray-400 mt-1">仓库根即 Unity 工程根时，可与 Unity 项目路径填相同目录</p></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-gray-500 mb-1">Git SSH 密钥路径（可选）</label><p class="text-xs text-gray-400 mt-0.5 mb-1">本机 Git/SSH 已配置时可留空；Jenkins 构建将使用系统默认 SSH 认证</p><div class="flex gap-2"><input type="text" id="editProjectGitSshKey" class="flex-1 min-w-0 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('editProjectGitSshKey','file',this)" class="px-3 py-1.5 border border-gray-200 rounded-lg text-xs text-gray-700 bg-white hover:bg-gray-50 shrink-0">浏览</button></div></div>
                    <div><label class="block text-xs font-medium text-gray-500 mb-1">默认 Git 分支</label><input type="text" id="editProjectDefaultGitBranch" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm"></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-gray-500 mb-1">Git 分支列表（每行一个）</label><textarea id="editProjectGitBranches" rows="2" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-xs"></textarea></div>
                    <div class="md:col-span-2"><label class="block text-xs font-medium text-gray-500 mb-1">Unity 项目路径（可选）</label><div class="flex gap-2"><input type="text" id="editProjectUnityProjectPath" class="flex-1 min-w-0 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><button type="button" onclick="openPathPicker('editProjectUnityProjectPath','dir',this)" class="px-3 py-1.5 border border-gray-200 rounded-lg text-xs text-gray-700 bg-white hover:bg-gray-50 shrink-0">浏览</button></div></div>
                    <div class="md:col-span-2 flex items-center gap-2"><button type="button" id="editProjectValidateGitBtn" class="px-3 py-1.5 bg-gray-200 rounded text-xs hover:bg-gray-300">验证 Git 配置</button><span id="editProjectGitValidateResult" class="text-xs"></span></div>
                </div>
            </details>
            <div class="grid grid-cols-1 md:grid-cols-2 gap-4">
                <div><label class="block text-xs font-medium text-gray-500 mb-1">可查看用户</label><input type="text" id="editProjectViewers" placeholder="多个用户名用逗号分隔" class="w-full px-3 py-1.5 border border-gray-200 rounded-lg text-sm focus:ring-2 focus:ring-blue-500"></div>
                <div><label class="block text-xs font-medium text-gray-500 mb-1">项目参与人员（可编辑）</label><div class="flex gap-2"><input type="text" id="editParticipantUser" placeholder="输入用户名" class="flex-1 px-3 py-1.5 border border-gray-200 rounded-lg text-sm"><button type="button" onclick="addEditParticipant()" class="px-3 py-1.5 bg-indigo-100 text-indigo-700 rounded-lg text-sm">验证并添加</button></div><ul id="editParticipantsList" class="mt-2 space-y-1 text-sm"></ul></div>
            </div>
            <div><label class="block text-xs font-medium text-gray-500 mb-1">可用渠道（不勾选=该项目的版本可使用全部渠道）</label><div id="editProjectChannels" class="mt-2 flex flex-wrap gap-x-4 gap-y-1"></div></div>
        </div>
        <div class="px-6 py-4 border-t border-gray-100 bg-gray-50/50 flex justify-end gap-2 flex-shrink-0">
            <button type="button" onclick="document.getElementById('editProjectModal').classList.add('hidden')" class="px-4 py-2.5 text-gray-700 bg-white border border-gray-200 rounded-lg hover:bg-gray-50 font-medium text-sm transition">取消</button>
            <button type="button" onclick="saveEditProject()" class="px-5 py-2.5 bg-blue-600 text-white rounded-lg hover:bg-blue-700 font-medium text-sm shadow-sm transition">保存</button>
        </div>
    </div>
</div>
<script>
var allProjectsCache = [];
var newParticipants = [];
var editParticipants = [];
var _participantCtx = '';
var _pendingParticipantUser = '';
var ROLES = {{PROJECT_ROLES_JSON}};
var _channelsCache = [];
var ALL_CHANNELS = {{ALL_CHANNELS_JSON}};
function parseUserList(str){ return (str||'').split(/[,，\\s]+/).map(function(s){ return s.trim(); }).filter(Boolean); }
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
    var gitBranches = branchesText ? branchesText.split(/\\n/).map(function(s){ return s.trim(); }).filter(Boolean) : [];
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
    setVal(prefix+'GitBranches', Array.isArray(branches) ? branches.join('\\n') : String(branches||''));
}
var _newGitBtn = document.getElementById('newProjectValidateGitBtn'); if(_newGitBtn) _newGitBtn.onclick=function(){ validateProjectGit('newProject', 'newProjectGitValidateResult'); };
var _editGitBtn = document.getElementById('editProjectValidateGitBtn'); if(_editGitBtn) _editGitBtn.onclick=function(){ validateProjectGit('editProject', 'editProjectGitValidateResult'); };
function renderNewParticipants(){ var ul=document.getElementById('newParticipantsList'); if(!ul) return; ul.innerHTML=newParticipants.map(function(p){ return '<li class="flex justify-between items-center py-1"><span>'+p.user+' <span class="text-gray-500">('+p.role+')</span></span><span><button type="button" onclick="editParticipantRole(\\'new\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-blue-600 text-xs mr-1">编辑</button><button type="button" onclick="removeParticipant(\\'new\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-red-600 text-xs">删除</button></span></li>'; }).join('') || '<li class="text-gray-400 text-xs">暂无参与人员</li>'; }
function renderEditParticipants(){ var ul=document.getElementById('editParticipantsList'); if(!ul) return; ul.innerHTML=editParticipants.map(function(p){ return '<li class="flex justify-between items-center py-1"><span>'+p.user+' <span class="text-gray-500">('+p.role+')</span></span><span><button type="button" onclick="editParticipantRole(\\'edit\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-blue-600 text-xs mr-1">编辑</button><button type="button" onclick="removeParticipant(\\'edit\\','+JSON.stringify(p.user).replace(/</g,'\\u003c')+')" class="text-red-600 text-xs">删除</button></span></li>'; }).join('') || '<li class="text-gray-400 text-xs">暂无参与人员</li>'; }
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
        var iconHtml = p.icon ? '<img src="'+p.icon+'" alt="" class="w-8 h-8 rounded-lg object-cover ring-1 ring-slate-200/80" onerror="this.style.display=\\'none\\'">' : '<span class="inline-flex items-center justify-center w-8 h-8 rounded-lg bg-slate-100 text-slate-400 text-xs"><i class="fas fa-folder"></i></span>';
        var phaseLabel = p.phase_label || p.phase || '-';
        var introSnip = (p.intro||'').slice(0,20); if((p.intro||'').length>20) introSnip+='…';
        var dateStr = (p.created_at||'').slice(0,19).replace('T',' ') || '-';
        var canEdit = p.can_edit;
        var statusBadge = (p.status==='archived') ? ' <span class="px-2 py-0.5 rounded text-xs bg-gray-200 text-gray-600">已归档</span>' : ((p.is_template) ? ' <span class="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">模板</span>' : '');
        var archiveBtn = canEdit && p.status!=='archived'
            ? '<button onclick="archiveProject(\\''+p.id+'\\', true)" class="inline-flex items-center whitespace-nowrap px-2.5 py-1 text-xs text-slate-600 bg-slate-50 hover:bg-slate-100 rounded-lg">归档</button>'
            : (canEdit && p.status==='archived'
                ? '<button onclick="archiveProject(\\''+p.id+'\\', false)" class="inline-flex items-center whitespace-nowrap px-2.5 py-1 text-xs text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded-lg">取消归档</button>'
                : '');
        var actions = '<a href="/admin/projects/'+p.id+'" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs font-medium text-amber-700 bg-amber-50 hover:bg-amber-100 rounded">项目中心</a>'
            + '<a href="/admin/projects/'+p.id+'/tasks" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-indigo-700 bg-indigo-50 hover:bg-indigo-100 rounded">任务</a>'
            + '<a href="/admin/projects/'+p.id+'/versions" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-emerald-700 bg-emerald-50 hover:bg-emerald-100 rounded">版本</a>';
        if(canEdit){
            actions += '<button onclick="editProject(\\''+p.id+'\\')" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-blue-700 bg-blue-50 hover:bg-blue-100 rounded">编辑</button>';
            actions += '<button onclick="deleteProject(\\''+p.id+'\\')" class="inline-flex items-center whitespace-nowrap px-2 py-1 text-xs text-red-700 bg-red-50 hover:bg-red-100 rounded">删除</button>';
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
</script>
'''


def render_projects_page() -> str:
    import json
    import re

    from models.data import channels_db
    from routes.admin.project_constants import PROJECT_PHASES, PROJECT_ROLES

    def _safe_json_for_script(value: object) -> str:
        text = value if isinstance(value, str) else json.dumps(value, ensure_ascii=False)
        return re.sub(r"(?i)</script>", r"<\\u002fscript>", text)

    phase_options = "".join(
        '<option value="%s">%s</option>' % (k, v) for k, v in PROJECT_PHASES
    )
    role_options = "".join('<option value="%s">%s</option>' % (r, r) for r in PROJECT_ROLES)
    all_channels = [
        {
            "id": (c.get("id") or "").strip(),
            "name": (c.get("name") or c.get("id") or "").strip(),
        }
        for c in (channels_db if isinstance(channels_db, list) else [])
        if (c.get("id") or "").strip()
    ]
    return (
        PROJECTS_PAGE.replace("{{PROJECT_PHASE_OPTIONS}}", phase_options)
        .replace("{{PROJECT_ROLE_OPTIONS}}", role_options)
        .replace("{{PROJECT_ROLES_JSON}}", _safe_json_for_script(PROJECT_ROLES))
        .replace("{{ALL_CHANNELS_JSON}}", _safe_json_for_script(all_channels))
    )
