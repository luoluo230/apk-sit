# -*- coding: utf-8 -*-
"""首页、健康检查"""

import html as html_module
import os
import logging
from collections import defaultdict
from datetime import datetime
from urllib.parse import quote
from flask import Blueprint, render_template_string, session, abort, request

from config import Config
from services.authz import can_access_module, is_admin, login_required
from models.data import (
    projects_db, download_stats, extract_package_info, extract_project_name,
    get_total_downloads, can_view_project, changelog_db, project_versions_db,
    get_channel_for_apk, get_changelog_for_file, iter_package_files,
)

logger = logging.getLogger(__name__)
bp = Blueprint('home', __name__)


def _get_visible_apk_files(username):
    """返回当前用户有权限查看的项目下安装包列表及统计。"""
    files = []
    total_size = 0
    if not os.path.exists(Config.APK_DIR):
        return [], 0, 0, 0
    for filename, filepath in iter_package_files():
        project_id = extract_project_name(filename)
        if not can_view_project(project_id, username):
            continue
        file_info = extract_package_info(filename, filepath)
        files.append(file_info)
        total_size += file_info['size']
    total_downloads = sum(
        download_stats.get(f['name'], 0)
        for f in files
    )
    active_projects = len(set(f['project'] for f in files))
    return files, total_size, total_downloads, active_projects


# 首页 HTML 模板：统一 slate/indigo 风格，导航清晰、操作友好
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .nav-bar {{ background: linear-gradient(135deg, #1e293b 0%, #334155 100%); }}
        .card-hover {{ transition: box-shadow 0.2s, transform 0.2s; }}
        .card-hover:hover {{ box-shadow: 0 10px 40px -12px rgba(0,0,0,0.15); transform: translateY(-1px); }}
        .btn-download {{ background: linear-gradient(135deg, #4f46e5 0%, #6366f1 100%); }}
        .btn-download:hover {{ background: linear-gradient(135deg, #4338ca 0%, #4f46e5 100%); }}
        .stat-card {{ background: linear-gradient(145deg, #ffffff 0%, #f8fafc 100%); }}
    </style>
</head>
<body class="bg-slate-50 min-h-screen text-slate-800 antialiased">
    <!-- 顶部导航 -->
    <header class="nav-bar shadow-lg sticky top-0 z-40">
        <div class="container mx-auto px-4">
            <div class="flex items-center justify-between h-14 md:h-16">
                <a href="/download-center" class="flex items-center gap-3 hover:opacity-90 transition">
                    <span class="flex items-center justify-center w-9 h-9 rounded-xl bg-white/10 text-white">
                        <i class="fas fa-box-open text-lg"></i>
                    </span>
                    <span class="text-lg md:text-xl font-bold text-white tracking-tight">APK 下载中心</span>
                </a>
                <nav class="flex items-center gap-2 md:gap-4">
                    <span class="text-sm text-slate-200 hidden sm:inline">👤 {current_user}</span>
                    <a href="/profile" class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-200 hover:bg-white/10 hover:text-white transition">个人中心</a>
                    <a href="/workspace" class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-200 hover:bg-white/10 hover:text-white transition"><i class="fas fa-briefcase"></i> 工作区</a>
                    {my_tasks_link}
                    {admin_link}
                    <a href="/logout" class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-200 hover:bg-white/10 hover:text-white transition">退出</a>
                </nav>
            </div>
        </div>
    </header>

    <main class="container mx-auto px-4 py-6 md:py-8 max-w-6xl">
        <!-- 欢迎与统计 -->
        <section class="mb-8">
            <h2 class="text-xl md:text-2xl font-bold text-slate-800 mb-1">欢迎使用</h2>
            <p class="text-slate-600 text-sm md:text-base mb-6">选择项目下的 APK 进行下载或扫码安装</p>
            <div class="grid grid-cols-2 lg:grid-cols-4 gap-4">
                <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-5 card-hover">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs font-medium text-slate-500 uppercase tracking-wider">安装包数量</p>
                            <p class="text-2xl font-bold text-slate-800 mt-0.5">{total_count}</p>
                        </div>
                        <div class="w-12 h-12 rounded-xl bg-indigo-100 flex items-center justify-center">
                            <i class="fas fa-box-open text-indigo-600 text-xl"></i>
                        </div>
                    </div>
                </div>
                <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-5 card-hover">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs font-medium text-slate-500 uppercase tracking-wider">总下载量</p>
                            <p class="text-2xl font-bold text-slate-800 mt-0.5">{total_downloads}</p>
                        </div>
                        <div class="w-12 h-12 rounded-xl bg-emerald-100 flex items-center justify-center">
                            <i class="fas fa-download text-emerald-600 text-xl"></i>
                        </div>
                    </div>
                </div>
                <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-5 card-hover">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs font-medium text-slate-500 uppercase tracking-wider">总大小</p>
                            <p class="text-2xl font-bold text-slate-800 mt-0.5">{total_size_mb} MB</p>
                        </div>
                        <div class="w-12 h-12 rounded-xl bg-violet-100 flex items-center justify-center">
                            <i class="fas fa-hdd text-violet-600 text-xl"></i>
                        </div>
                    </div>
                </div>
                <div class="stat-card rounded-2xl border border-slate-200/80 shadow-sm p-5 card-hover">
                    <div class="flex items-center justify-between">
                        <div>
                            <p class="text-xs font-medium text-slate-500 uppercase tracking-wider">活跃项目</p>
                            <p class="text-2xl font-bold text-slate-800 mt-0.5">{active_projects}</p>
                        </div>
                        <div class="w-12 h-12 rounded-xl bg-amber-100 flex items-center justify-center">
                            <i class="fas fa-folder text-amber-600 text-xl"></i>
                        </div>
                    </div>
                </div>
            </div>
        </section>

        <!-- 搜索与操作栏 -->
        <section class="bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden mb-6">
            {project_filter_hint}
            <div class="p-4 md:p-5 flex flex-col sm:flex-row gap-3 sm:items-center">
                <div class="flex-1 relative">
                    <i class="fas fa-search absolute left-4 top-1/2 -translate-y-1/2 text-slate-400 text-sm"></i>
                    <input type="text" id="searchInput" placeholder="搜索安装包名称、平台或项目…" class="w-full pl-10 pr-4 py-2.5 rounded-xl border border-slate-200 focus:ring-2 focus:ring-indigo-500/30 focus:border-indigo-500 text-slate-800 placeholder-slate-400 text-sm transition" onkeyup="filterFiles()">
                </div>
                <select id="channelFilter" onchange="filterFiles()" class="px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 text-sm focus:ring-2 focus:ring-indigo-500/30">
                    <option value="">全部渠道</option>
                    <option value="dev">开发</option>
                    <option value="release">正式</option>
                    <option value="test">测试</option>
                    <option value="beta">Beta</option>
                </select>
                <select id="platformFilter" onchange="filterFiles()" class="px-4 py-2.5 rounded-xl border border-slate-200 text-slate-700 text-sm focus:ring-2 focus:ring-indigo-500/30">
                    <option value="">全部平台</option>
                    <option value="android">Android</option>
                    <option value="ios">iOS</option>
                </select>
                <div class="flex gap-2 flex-shrink-0">
                    {upload_btn}
                    <button type="button" onclick="location.reload()" class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl border border-slate-200 bg-white text-slate-700 text-sm font-medium hover:bg-slate-50 hover:border-slate-300 transition">
                        <i class="fas fa-sync-alt text-slate-500"></i> 刷新
                    </button>
                </div>
            </div>
        </section>

        <!-- 按项目分组的 APK 列表 -->
        <section class="space-y-6">
            {files_html}
        </section>

        {empty_tip}
    </main>

        <!-- 安装包下载详情（与项目版本页一致） -->
    <div id="apkDetailModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden items-center justify-center z-50 p-4" onclick="closeApkDetail(event)">
        <div class="bg-white rounded-2xl shadow-2xl w-full max-w-3xl max-h-[90vh] overflow-hidden flex flex-col" onclick="event.stopPropagation()">
            <div class="px-6 py-4 border-b border-slate-100 flex items-center justify-between shrink-0">
                <h3 class="text-lg font-semibold text-slate-800 flex items-center gap-2"><i class="fas fa-download text-emerald-500"></i> 安装包下载</h3>
                <button type="button" onclick="closeApkDetail()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>
            </div>
            <div id="apkDetailBody" class="p-6 overflow-y-auto flex-1 text-sm">加载中…</div>
        </div>
    </div>

<!-- 上传弹窗 -->
    <div id="uploadModal" class="fixed inset-0 bg-slate-900/60 backdrop-blur-sm hidden items-center justify-center z-50 p-4" onclick="closeUpload(event)">
        <div class="bg-white rounded-2xl shadow-2xl max-w-md w-full mx-auto p-6 border border-slate-100" onclick="event.stopPropagation()">
            <h3 class="text-lg font-semibold text-slate-800 mb-4 flex items-center gap-2">
                <i class="fas fa-upload text-emerald-500"></i> 上传安装包
            </h3>
            <form id="uploadForm">
                <div class="mb-4">
                    <input type="file" name="file" accept=".apk,.ipa" class="w-full px-4 py-3 border border-slate-200 rounded-xl text-sm file:mr-4 file:py-2 file:px-4 file:rounded-lg file:border-0 file:bg-indigo-50 file:text-indigo-700 file:font-medium file:cursor-pointer hover:file:bg-indigo-100" required>
                </div>
                <p class="text-sm text-slate-500 mb-4">支持 Android `.apk` 与 iOS `.ipa`，单文件建议不超过 100MB。</p>
                <div id="uploadProgress" class="mb-4 hidden">
                    <div class="h-2 bg-slate-200 rounded-full overflow-hidden">
                        <div id="progressBar" class="h-full bg-indigo-600 rounded-full transition-all duration-300" style="width: 0%"></div>
                    </div>
                    <p id="uploadStatus" class="text-sm text-slate-600 mt-2"></p>
                </div>
                <div class="flex gap-3">
                    <button type="button" onclick="closeUpload()" class="flex-1 py-2.5 rounded-xl border border-slate-200 text-slate-700 font-medium hover:bg-slate-50 transition">取消</button>
                    <button type="submit" class="flex-1 py-2.5 rounded-xl btn-download text-white font-medium shadow-sm hover:shadow transition">上传</button>
                </div>
            </form>
        </div>
    </div>

    <script>
        function filterFiles() {{
            var q = (document.getElementById("searchInput").value || "").toLowerCase().trim();
            var ch = (document.getElementById("channelFilter") && document.getElementById("channelFilter").value || "").toLowerCase();
            var platform = (document.getElementById("platformFilter") && document.getElementById("platformFilter").value || "").toLowerCase();
            document.querySelectorAll(".project-group").forEach(function(group) {{
                var hasVisible = false;
                group.querySelectorAll(".file-item").forEach(function(el) {{
                    var name = el.getAttribute("data-name") || "";
                    var project = el.getAttribute("data-project") || "";
                    var channel = el.getAttribute("data-channel") || "";
                    var itemPlatform = el.getAttribute("data-platform") || "";
                    var show = (!q || name.indexOf(q) >= 0 || project.indexOf(q) >= 0 || itemPlatform.indexOf(q) >= 0) && (!ch || channel === ch) && (!platform || itemPlatform === platform);
                    el.style.display = show ? "" : "none";
                    if (show) hasVisible = true;
                }});
                group.style.display = hasVisible ? "" : "none";
            }});
        }}
        function escHtml(s) {{
            if (s == null) return "";
            return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
        }}
        function renderApkDownloadPanel(d) {{
            if (!d || !d.available) return "<p class=\\"text-slate-500 text-sm py-4\\">暂无可下载的安装包</p>";
            var row = function(label, val) {{ return "<div class=\\"flex gap-2 py-1\\"><span class=\\"text-slate-400 w-20 shrink-0\\">" + label + "</span><span class=\\"text-slate-800 break-all flex-1\\">" + val + "</span></div>"; }};
            var qrBlock = function(title, url, qr) {{
                if (!url) return "";
                var img = qr ? "<img src=\\"" + qr + "\\" alt=\\"QR\\" class=\\"w-36 h-36 object-contain rounded-lg border border-slate-100 bg-white p-1\\">" : "<p class=\\"text-slate-400 text-xs\\">无二维码</p>";
                return "<div class=\\"rounded-xl border border-slate-200 p-4 bg-slate-50/50\\"><p class=\\"text-xs font-semibold text-slate-600 mb-2\\">" + title + "</p>" + img + "<p class=\\"text-[11px] text-slate-500 mt-2 break-all\\">" + escHtml(url) + "</p><a href=\\"" + escHtml(url) + "\\" target=\\"_blank\\" rel=\\"noopener\\" class=\\"inline-flex mt-2 text-indigo-600 text-xs hover:underline\\">打开链接</a></div>";
            }};
            var html = "<div class=\\"space-y-4\\">";
            html += row("构建时间", escHtml(d.build_time || "—"));
            html += row("包名", escHtml(d.package_name || d.app_name || "—"));
            html += row("文件", escHtml(d.file_name || "—"));
            html += row("大小", escHtml(d.size_label || "—"));
            html += row("渠道/阶段", escHtml((d.channel_label || d.channel || "-") + " / " + (d.stage_label || d.stage || "-")));
            html += "<div class=\\"grid md:grid-cols-2 gap-4 pt-2\\">";
            html += qrBlock("本地下载", d.local_download_url, d.local_qr_dataurl);
            html += qrBlock("远端下载", d.oss_download_url, d.oss_qr_dataurl);
            html += "</div>";
            if (d.pub_download_path) {{
                html += "<div class=\\"pt-2\\"><a href=\\"/pub/download/" + escHtml(d.pub_download_path) + "\\" class=\\"inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-emerald-600 text-white text-sm hover:bg-emerald-700\\"><i class=\\"fas fa-download\\"></i>直接下载</a></div>";
            }}
            html += "</div>";
            return html;
        }}
        function showApkDetail(relPath) {{
            var modal = document.getElementById("apkDetailModal");
            var body = document.getElementById("apkDetailBody");
            if (!modal || !body) return;
            body.innerHTML = "<p class=\\"text-slate-400 text-sm\\">加载中…</p>";
            modal.classList.remove("hidden");
            modal.classList.add("flex");
            fetch("/api/download-center/apk-info?path=" + encodeURIComponent(relPath), {{ credentials: "same-origin" }})
                .then(function(r) {{ return r.json(); }})
                .then(function(d) {{
                    if (d.error && !d.available) {{ body.innerHTML = "<p class=\\"text-red-500 text-sm\\">" + escHtml(d.error || "加载失败") + "</p>"; return; }}
                    body.innerHTML = renderApkDownloadPanel(d);
                }})
                .catch(function() {{ body.innerHTML = "<p class=\\"text-red-500 text-sm\\">加载失败</p>"; }});
        }}
        function closeApkDetail(e) {{
            if (!e || e.target === e.currentTarget) {{
                document.getElementById("apkDetailModal").classList.add("hidden");
                document.getElementById("apkDetailModal").classList.remove("flex");
            }}
        }}
        function showUploadModal() {{
            document.getElementById("uploadModal").classList.remove("hidden");
            document.getElementById("uploadModal").classList.add("flex");
        }}
        function closeUpload(e) {{
            if (!e || e.target === e.currentTarget) {{
                document.getElementById("uploadModal").classList.add("hidden");
                document.getElementById("uploadModal").classList.remove("flex");
                document.getElementById("uploadForm").reset();
                document.getElementById("uploadProgress").classList.add("hidden");
            }}
        }}
        document.getElementById("uploadForm").addEventListener("submit", function(e) {{
            e.preventDefault();
            var progress = document.getElementById("uploadProgress");
            var bar = document.getElementById("progressBar");
            var status = document.getElementById("uploadStatus");
            progress.classList.remove("hidden");
            status.textContent = "正在上传…";
            bar.style.width = "30%";
            var formData = new FormData(this);
            fetch("/upload", {{ method: "POST", body: formData, credentials: "same-origin" }})
                .then(function(r) {{ return r.json(); }})
                .then(function(data) {{
                    bar.style.width = "100%";
                    if (data.success) {{
                        status.textContent = "上传成功，正在刷新…";
                        setTimeout(function() {{ closeUpload(); location.reload(); }}, 800);
                    }} else {{
                        status.textContent = "上传失败: " + (data.error || "未知错误");
                        status.classList.add("text-red-600");
                    }}
                }})
                .catch(function(err) {{
                    status.textContent = "上传失败: " + (err.message || "网络错误");
                    status.classList.add("text-red-600");
                }});
        }});
    </script>
</body>
</html>
'''


def _build_files_html(grouped_files, projects_db, changelog_db=None, project_versions_db=None):
    """生成按项目分组的 APK 列表 HTML；支持渠道与推荐标识。"""
    changelog_db = changelog_db or {}
    project_versions_db = project_versions_db or {}
    channel_labels = {'dev': '开发', 'release': '正式', 'test': '测试', 'beta': 'Beta'}
    if not grouped_files:
        return ''
    out = []
    for project_id, project_files in grouped_files.items():
        project_name = (projects_db.get(project_id) or {}).get('name', project_id)
        project_icon = (projects_db.get(project_id) or {}).get('icon', '')
        icon_html = ''
        if project_icon:
            icon_html = '<img src="' + project_icon + '" alt="" class="w-8 h-8 rounded-lg object-cover">'
        else:
            icon_html = '<span class="w-8 h-8 rounded-lg bg-slate-200 flex items-center justify-center text-slate-500"><i class="fas fa-folder text-sm"></i></span>'
        versions = project_versions_db.get(project_id) or []
        out.append(
            '<div class="project-group bg-white rounded-2xl border border-slate-200/80 shadow-sm overflow-hidden">'
            '<div class="px-5 py-4 bg-gradient-to-r from-slate-50 to-white border-b border-slate-100 flex items-center gap-3">'
            + icon_html +
            '<h3 class="font-semibold text-slate-800">' + project_name + '</h3>'
            '<span class="text-xs text-slate-500">' + str(len(project_files)) + ' 个包</span>'
            '</div><div class="divide-y divide-slate-100">'
        )
        for f in project_files:
            raw_name = f['name']
            ch_text, recommended = get_changelog_for_file(raw_name)
            rec_badge = '<span class="ml-1.5 px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">推荐</span>' if recommended else ''
            channel = get_channel_for_apk(project_id, raw_name, versions)
            ch_label = channel_labels.get(channel, channel) if channel else ''
            ch_badge = '<span class="ml-1 px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600">' + html_module.escape(ch_label) + '</span>' if ch_label else ''
            platform_badge = '<span class="ml-1 px-2 py-0.5 rounded text-xs bg-sky-100 text-sky-700">' + html_module.escape(f.get('platform_label') or '-') + '</span>'
            name_esc = html_module.escape(raw_name, quote=True)
            name_attr = name_esc
            download_href = '/download/' + quote(raw_name, safe='')
            badges = platform_badge + ch_badge + rec_badge
            out.append(
                '<div class="file-item p-4 md:p-5 hover:bg-slate-50/80 transition flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3" data-name="' + raw_name.lower() + '" data-project="' + (f.get('project') or '').lower() + '" data-channel="' + (channel or '').lower() + '" data-platform="' + (f.get('platform') or '').lower() + '">'
                '<div class="min-w-0 flex-1">'
                '<div class="font-medium text-slate-800 truncate">' + name_esc + badges + '</div>'
                '<div class="text-sm text-slate-500 mt-0.5">' + html_module.escape(f.get('app_name') or '-') + ' · v' + html_module.escape(str(f.get('version') or '-')) + ' · ' + str(f.get('size_mb', 0)) + ' MB · ' + html_module.escape(str(f.get('date') or '')) + '</div>'
                '</div>'
                '<div class="flex gap-2 flex-shrink-0">'
                '<button type="button" data-path="' + name_attr + '" onclick="showApkDetail(this.getAttribute(\'data-path\'))" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl border border-slate-200 bg-white text-slate-700 text-sm font-medium hover:bg-slate-50 hover:border-slate-300 transition">'
                '<i class="fas fa-qrcode text-slate-500"></i> 详情</button>'
                '<button type="button" data-path="' + name_attr + '" onclick="showApkDetail(this.getAttribute(\'data-path\'))" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-xl btn-download text-white text-sm font-medium shadow-sm hover:shadow transition">'
                '<i class="fas fa-download"></i> 下载</button>'
                '</div></div>'
            )
        out.append('</div></div>')
    return ''.join(out)


@bp.route('/download-center')
@login_required
def download_center():
    username = session.get('user') or ''
    project_filter = (request.args.get('project') or '').strip()
    try:
        files, total_size, total_downloads, active_projects = _get_visible_apk_files(username)
        grouped = defaultdict(list)
        for f in files:
            if project_filter and f.get('project') != project_filter:
                continue
            grouped[f['project']].append(f)
        for project_id in grouped:
            def _rec_first(f):
                ch = changelog_db.get(f.get('name'))
                return (bool(isinstance(ch, dict) and ch.get('recommended')), f.get('timestamp', 0))
            grouped[project_id].sort(key=_rec_first, reverse=True)
        # 按项目名称排序展示
        def project_sort_key(pid):
            return (projects_db.get(pid, {}).get('name', pid), pid)
        grouped = dict(sorted(grouped.items(), key=lambda x: project_sort_key(x[0])))
        total_size_mb = f"{total_size / 1024 / 1024:.1f}" if total_size > 0 else "0"
        files_html = _build_files_html(grouped, projects_db, changelog_db, project_versions_db)
        current_user = username or '访客'
        admin_link = ''
        if is_admin():
            admin_link = '<a href="/admin" class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-200 hover:bg-white/10 hover:text-white transition"><i class="fas fa-cog"></i> 管理中心</a>'
        my_tasks_link = ''
        if can_access_module('projects'):
            my_tasks_link = '<a href="/admin/my-tasks" class="inline-flex items-center gap-1.5 px-3 py-2 rounded-lg text-sm font-medium text-slate-200 hover:bg-white/10 hover:text-white transition"><i class="fas fa-tasks"></i> 我的任务</a>'
        upload_btn = ''
        if is_admin():
            upload_btn = '<button type="button" onclick="showUploadModal()" class="inline-flex items-center gap-2 px-4 py-2.5 rounded-xl bg-emerald-600 text-white text-sm font-medium hover:bg-emerald-700 shadow-sm transition"><i class="fas fa-upload"></i> 上传安装包</button>'
        else:
            upload_btn = ''
        empty_tip = ''
        if not files:
            admin_extra = ''
            if is_admin():
                admin_extra = '<p class="text-xs mt-3"><a href="/admin/projects" class="text-indigo-600 hover:text-indigo-700 font-medium">→ 前往项目管理</a> 添加项目、配置成员；或点击上方「上传安装包」按钮直接上传。</p>'
            empty_tip = '''<div class="text-center py-16 px-4 rounded-2xl border-2 border-dashed border-slate-200 bg-slate-50/50">
                <div class="w-16 h-16 mx-auto rounded-2xl bg-slate-200/80 flex items-center justify-center mb-4">
                    <i class="fas fa-inbox text-3xl text-slate-400"></i>
                </div>
                <p class="text-base font-medium text-slate-700">暂无可见的 APK</p>
                <p class="text-sm text-slate-500 mt-1">您可能尚无项目查看权限，或平台尚未上传任何 APK。</p>
                <p class="text-xs text-slate-400 mt-2">请联系管理员在「项目管理」中为您分配项目权限。</p>
                ''' + admin_extra + '''
            </div>'''
        project_filter_hint = ''
        if project_filter and project_filter in projects_db:
            pname = (projects_db.get(project_filter) or {}).get('name', project_filter)
            project_filter_hint = '<div class="px-4 py-2 bg-indigo-50 border-b border-indigo-100 text-sm text-indigo-800 flex items-center gap-2"><i class="fas fa-filter text-indigo-500"></i> 当前筛选：' + html_module.escape(pname) + ' <a href="/download-center" class="ml-2 text-indigo-600 hover:underline">清除筛选</a></div>'
        return render_template_string(
            HTML_TEMPLATE.format(
                files_html=files_html,
                total_count=len(files),
                total_size_mb=total_size_mb,
                current_user=current_user,
                admin_link=admin_link,
                my_tasks_link=my_tasks_link,
                upload_btn=upload_btn,
                total_downloads=total_downloads,
                active_projects=active_projects,
                empty_tip=empty_tip,
                project_filter_hint=project_filter_hint,
            )
        )
    except Exception as e:
        logger.error("首页加载失败：%s", e, exc_info=True)
        abort(500)




def _parse_apk_path_hierarchy(rel_path: str) -> dict:
    parts = (rel_path or "").replace("\\", "/").split("/")
    if len(parts) >= 2:
        return {"channel_subdir": parts[0], "stage": parts[1]}
    return {}


@bp.route('/api/download-center/apk-info')
@login_required
def download_center_apk_info():
    from flask import jsonify
    from services.apk_artifact_service import read_apk_meta, build_download_info
    from models.data import can_view_project

    rel_path = (request.args.get('path') or '').strip().replace('\\', '/')
    if not rel_path or '..' in rel_path or rel_path.startswith('/'):
        return jsonify({'error': 'invalid path'}), 400
    full = os.path.normpath(os.path.join(Config.APK_DIR, rel_path))
    base = os.path.normpath(Config.APK_DIR)
    if not full.startswith(base) or not os.path.isfile(full):
        return jsonify({'error': '文件不存在'}), 404
    project_id = extract_project_name(rel_path)
    username = session.get('user') or ''
    if project_id and not can_view_project(project_id, username):
        return jsonify({'error': '无权限'}), 403

    meta = read_apk_meta(full)
    fake_version = {
        'id': meta.get('version_id') or '',
        'version_name': meta.get('version_name') or '',
        'version_code': meta.get('version_code') or '',
        'channel': meta.get('channel') or '',
        'stage': meta.get('stage') or _parse_apk_path_hierarchy(rel_path).get('stage') or 'dev',
        'platform': 'android',
        'apk_path': rel_path,
        'apk_download': meta,
        'package_name': meta.get('package_name') or '',
    }
    info = build_download_info(project_id, fake_version)
    if not info:
        return jsonify({'error': '无法读取安装包信息'}), 404
    return jsonify(info)


@bp.route('/health')
def health():
    from flask import jsonify
    package_count = sum(1 for _ in iter_package_files())
    return jsonify({'status': 'ok', 'apk_count': package_count, 'package_count': package_count, 'timestamp': datetime.now().isoformat()})
