# -*- coding: utf-8 -*-
"""文档中心：商业化知识门户，支持模块分类、标签、模板、权限管理"""

import os
import html
import json as json_module
import uuid
from datetime import datetime, timedelta

from flask import Blueprint, request, jsonify, session, send_file
from werkzeug.utils import secure_filename

try:
    from flask_wtf.csrf import generate_csrf
except ImportError:
    generate_csrf = lambda: ''

from config import Config, DATA_DIR
from models.data import get_project_record, projects_db, resolve_project_id
from services.authz import admin_required, is_super_admin_or_admin
from utils import load_json, save_json

bp = Blueprint('docs', __name__)

# 数据文件
DOCS_FILE = os.path.join(DATA_DIR, 'documents.json')
DOCS_META_FILE = os.path.join(DATA_DIR, 'documents_meta.json')

# 模块与分类（与六大业务模块对应）
DOC_MODULES = [
    ('projects', '项目中心'), ('build', '构建管理'), ('versions', '版本与发布'),
    ('download', '下载中心'), ('analytics', '数据分析'), ('jenkins', 'Jenkins 管理'),
    ('system', '系统设置'), ('general', '通用'),
]
DOC_CATEGORIES = [
    ('product', '产品说明'), ('guide', '使用指南'), ('ops', '运维手册'),
    ('api', 'API 文档'), ('faq', 'FAQ'), ('spec', '规范标准'), ('other', '其他'),
]
# 角色适用（用于文档头展示）
DOC_ROLES = [
    ('dev', '研发'), ('qa', '测试'), ('pm', '产品/项目经理'),
    ('ops', '运维'), ('admin', '管理员'),
]

DOC_TEMPLATES = {
    'product_module': {
        'title': '【产品模块说明】模板',
        'content': '''# 模块名称
（简要描述该模块的价值与目标）

## 核心功能
- 功能 1
- 功能 2
- 功能 3

## 适用角色
研发 / 测试 / 产品 / 运维

## 关键操作
1. 步骤一
2. 步骤二
3. 步骤三

## 常见问题
**Q:** 问题示例？
**A:** 回答示例

## 相关链接
- 相关功能入口
''',
        'module': 'general',
        'category': 'product',
    },
    'sop_release': {
        'title': '【发布流程 SOP】模板',
        'content': '''# 版本发布流程

## 前置检查
- [ ] 构建成功
- [ ] 测试通过
- [ ] Changelog 已更新

## 发布步骤
1. 进入项目中心 → 版本与发布
2. 确认 APK 已落盘
3. 标记推荐版本
4. 通知相关人员

## 回滚说明
（紧急回滚时的操作）

## 负责人
（角色/人员）
''',
        'module': 'versions',
        'category': 'spec',
    },
    'runbook': {
        'title': '【故障排查 Runbook】模板',
        'content': '''# 故障标题

## 现象
（用户/系统表现）

## 可能原因
1. 原因 1
2. 原因 2

## 排查步骤
1. 步骤一
2. 步骤二

## 解决方案
（具体操作命令或配置）

## 预防建议
（如何避免再次发生）

## 相关日志/配置
''',
        'module': 'system',
        'category': 'ops',
    },
    'faq': {
        'title': '【FAQ 知识库条目】模板',
        'content': '''# Q: 问题一句话描述

## 适用角色
研发 / 测试 / 运维

## 现象
（用户看到什么）

## 原因
（简要说明）

## 解决
（分步操作）

## 预防
（可选）
''',
        'module': 'general',
        'category': 'faq',
    },
}


def _docs_db():
    return load_json(DOCS_FILE, [])


def _save_docs(data):
    return save_json(DOCS_FILE, data)


def _attachments_dir():
    d = getattr(Config, 'DOCS_ATTACHMENTS_DIR', None) or os.path.join(
        os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'doc_attachments'
    )
    if not os.path.isabs(d):
        d = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), d))
    os.makedirs(d, exist_ok=True)
    return d


def _current_username():
    return session.get('user') or ''


def _can_view(doc, username):
    if not username:
        return False
    if doc.get('created_by') == username:
        return True
    perms = doc.get('permissions') or {}
    return username in perms.get('viewers', []) or username in perms.get('editors', [])


def _can_edit(doc, username):
    if not username:
        return False
    if doc.get('created_by') == username:
        return True
    perms = doc.get('permissions') or {}
    return username in perms.get('editors', [])


def _can_manage(doc, username):
    """能否管理权限（仅创建者）"""
    return doc.get('created_by') == username


def _can_delete(doc, username):
    """能否删除文档：创建者或超级管理员"""
    return doc.get('created_by') == username or is_super_admin_or_admin()




# ---------- 页面 ----------
def _module_label(m):
    return dict(DOC_MODULES).get(m, m) if m else '-'
def _category_label(c):
    return dict(DOC_CATEGORIES).get(c, c) if c else '-'


def _project_choices(selected_project_id=''):
    selected_project_id = resolve_project_id(selected_project_id) or str(selected_project_id or '').strip()
    rows = []
    if isinstance(projects_db, dict):
        for project_id, project in projects_db.items():
            payload = project if isinstance(project, dict) else {}
            rows.append(
                {
                    'id': str(project_id),
                    'name': str(payload.get('name') or project_id),
                    'status': str(payload.get('status') or 'active'),
                }
            )
    rows.sort(key=lambda item: (item['status'] == 'archived', item['name'].lower(), item['id'].lower()))
    if selected_project_id and all(item['id'] != selected_project_id for item in rows):
        rows.append({'id': selected_project_id, 'name': '%s（已缺失）' % selected_project_id, 'status': 'missing'})
    return rows


def _project_label(project_id):
    resolved_id, project = get_project_record(project_id)
    if isinstance(project, dict):
        return str(project.get('name') or resolved_id or project_id or '未绑定项目')
    return str(project_id or '未绑定项目')


@bp.route('/docs')
@admin_required('docs')
def docs_list_page():
    username = _current_username()
    filter_module = (request.args.get('module') or '').strip()
    filter_category = (request.args.get('category') or '').strip()
    filter_project = resolve_project_id((request.args.get('project_id') or '').strip()) or ''
    docs = [d for d in _docs_db() if _can_view(d, username)]
    docs.sort(key=lambda x: (bool(x.get('pinned')), x.get('updated_at', '')), reverse=True)
    # 统计
    now = datetime.now()
    week_ago = (now - timedelta(days=7)).isoformat()
    total = len(docs)
    recent_count = sum(1 for d in docs if (d.get('updated_at') or '') >= week_ago)
    my_count = sum(1 for d in docs if d.get('created_by') == username)
    att_count = sum(len(d.get('attachments') or []) for d in docs)
    pinned = [d for d in docs if d.get('pinned')]
    # 模块快捷卡片
    mod_cards = []
    for mid, mname in DOC_MODULES:
        count = sum(1 for d in docs if d.get('module') == mid)
        latest = next((d for d in docs if d.get('module') == mid), None)
        latest_title = (latest.get('title') or '无标题')[:20] + ('…' if len(latest.get('title') or '') > 20 else '') if latest else '-'
        href = '/docs?module=' + mid
        mod_cards.append(
            '<a href="%s" class="block p-4 rounded-xl border border-slate-200 hover:border-indigo-300 hover:bg-indigo-50/50 transition">'
            '<p class="text-xs font-medium text-slate-500 uppercase tracking-wide">%s</p>'
            '<p class="text-lg font-semibold text-slate-800 mt-0.5">%d</p>'
            '<p class="text-xs text-slate-400 mt-1 truncate">%s</p></a>' % (
                href, html.escape(mname), count, html.escape(latest_title)
            )
        )
    # 置顶文档
    pinned_html = ''
    if pinned:
        pinned_html = '<div class="mb-6"><h3 class="text-sm font-semibold text-slate-700 mb-3 flex items-center gap-2"><i class="fas fa-thumbtack text-amber-500"></i> 推荐文档</h3><div class="flex flex-wrap gap-2">'
        for d in pinned[:6]:
            pinned_html += '<a href="/docs/%s" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg bg-amber-50 border border-amber-100 text-amber-800 text-sm font-medium hover:bg-amber-100 transition">%s</a>' % (
                html.escape(d.get('id', '')), html.escape((d.get('title') or '无标题')[:30])
            )
        pinned_html += '</div></div>'
    # 模板入口
    tpl_btns = ''.join(
        '<a href="/docs/new?template=%s" class="px-4 py-2 rounded-lg border border-slate-200 text-slate-700 text-sm hover:bg-slate-50">%s</a>' % (
            html.escape(tid), html.escape(t.get('title', tid))[:18]
        ) for tid, t in list(DOC_TEMPLATES.items())[:4]
    )
    # 文档表格行
    rows = []
    for d in docs:
        if filter_module and d.get('module') != filter_module:
            continue
        if filter_category and d.get('category') != filter_category:
            continue
        if filter_project and (resolve_project_id(d.get('project_id')) or '') != filter_project:
            continue
        can_edit_ = _can_edit(d, username)
        can_del_ = _can_delete(d, username)
        acts = []
        if can_edit_:
            acts.append('<a href="/docs/%s/edit" class="text-indigo-600 hover:underline text-sm">编辑</a>' % html.escape(d.get('id', '')))
        if can_del_:
            acts.append('<button type="button" class="doc-del-btn text-red-600 hover:underline text-sm" data-id="%s">删除</button>' % html.escape(d.get('id', '')))
        project_badge = '<span class="px-2 py-0.5 rounded text-xs bg-emerald-50 text-emerald-700">%s</span>' % html.escape(_project_label(d.get('project_id')))
        mod_badge = '<span class="px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600">%s</span>' % html.escape(_module_label(d.get('module')))
        cat_badge = '<span class="px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700">%s</span>' % html.escape(_category_label(d.get('category')))
        pin_badge = '<span class="px-2 py-0.5 rounded text-xs bg-amber-100 text-amber-800">置顶</span>' if d.get('pinned') else ''
        tags_str = (d.get('tags') or '') if isinstance(d.get('tags'), str) else ','.join(d.get('tags') or [])
        tags_badges = ''.join('<span class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600">%s</span>' % html.escape(t.strip()) for t in tags_str.split(',') if t.strip())[:3]
        att_icon = '<i class="fas fa-paperclip text-slate-400 text-xs" title="有附件"></i>' if (d.get('attachments') or []) else ''
        rows.append(
            '<tr class="border-b border-gray-100 hover:bg-slate-50 doc-row" data-title="%s" data-creator="%s" data-tags="%s" data-module="%s" data-category="%s">'
            '<td class="px-4 py-3"><a href="/docs/%s" class="font-medium text-indigo-600 hover:underline">%s</a> %s <div class="flex flex-wrap gap-1 mt-1">%s %s %s %s %s</div></td>'
            '<td class="px-4 py-3 text-sm text-slate-500">%s</td>'
            '<td class="px-4 py-3 text-sm text-slate-500">%s</td>'
            '<td class="px-4 py-3 text-sm">%s</td></tr>' % (
                html.escape((d.get('title') or '')[:80]).replace('"', '&quot;'),
                html.escape(d.get('created_by', '')),
                html.escape(tags_str[:100]).replace('"', '&quot;'),
                html.escape(d.get('module') or ''),
                html.escape(d.get('category') or ''),
                html.escape(d.get('id', '')),
                html.escape((d.get('title') or '无标题')[:50]),
                pin_badge,
                project_badge,
                mod_badge,
                cat_badge,
                tags_badges,
                att_icon,
                html.escape(d.get('created_by', '')),
                (d.get('updated_at') or '')[:16] if d.get('updated_at') else '-',
                ' '.join(acts) if acts else '-'
            )
        )
    rows_html = ''.join(rows) if rows else '<tr><td colspan="4" class="px-4 py-12 text-center text-slate-500">暂无文档，可使用下方模板快速创建</td></tr>'
    filter_mod_opts = ''.join('<option value="%s"%s>%s</option>' % (mid, ' selected' if filter_module == mid else '', html.escape(mname)) for mid, mname in [('', '全部模块')] + list(DOC_MODULES))
    filter_cat_opts = ''.join('<option value="%s"%s>%s</option>' % (cid, ' selected' if filter_category == cid else '', html.escape(cname)) for cid, cname in [('', '全部分类')] + list(DOC_CATEGORIES))
    filter_project_opts = ''.join('<option value="%s"%s>%s</option>' % (html.escape(project['id']), ' selected' if filter_project == project['id'] else '', html.escape(project['name'])) for project in ([{'id': '', 'name': '鍏ㄩ儴椤圭洰'}] + _project_choices(filter_project)))
    content = '''
    <div class="space-y-6">
        <div class="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-4">
            <div>
                <h2 class="text-xl font-bold text-slate-800">知识中心</h2>
                <p class="text-sm text-slate-500 mt-0.5">项目文档、运维手册、FAQ 统一管理与协作</p>
            </div>
            <a href="/docs/new" class="inline-flex items-center gap-2 px-5 py-2.5 bg-indigo-600 text-white rounded-xl text-sm font-medium hover:bg-indigo-700 shadow-sm"><i class="fas fa-plus"></i> 新建文档</a>
        </div>
        <div class="grid grid-cols-2 md:grid-cols-4 gap-4">
            <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">文档总数</p>
                <p class="text-2xl font-bold text-slate-800 mt-0.5">%d</p>
            </div>
            <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">近 7 日更新</p>
                <p class="text-2xl font-bold text-indigo-600 mt-0.5">%d</p>
            </div>
            <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">我创建的</p>
                <p class="text-2xl font-bold text-slate-800 mt-0.5">%d</p>
            </div>
            <div class="bg-white rounded-xl border border-slate-200 p-4 shadow-sm">
                <p class="text-[11px] font-semibold text-slate-500 uppercase tracking-wider">附件总数</p>
                <p class="text-2xl font-bold text-slate-800 mt-0.5">%d</p>
            </div>
        </div>
        <div class="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-8 gap-3">
            %s
        </div>
        %s
        <div class="bg-white rounded-xl shadow-sm border border-slate-100 overflow-hidden">
            <div class="px-5 py-4 border-b bg-slate-50/50 flex flex-col sm:flex-row gap-3 sm:items-center">
                <h3 class="text-sm font-semibold text-slate-800">文档列表</h3>
                <div class="flex flex-wrap gap-2 flex-1">
                    <input type="text" id="docSearch" placeholder="搜索标题、创建者、标签…" class="flex-1 min-w-[160px] px-3 py-1.5 rounded-lg border border-slate-200 text-sm focus:ring-2 focus:ring-indigo-500/30">
                    <select id="docProjectFilter" class="px-3 py-1.5 rounded-lg border border-slate-200 text-sm">%s</select>
                    <select id="docModFilter" class="px-3 py-1.5 rounded-lg border border-slate-200 text-sm">%s</select>
                    <select id="docCatFilter" class="px-3 py-1.5 rounded-lg border border-slate-200 text-sm">%s</select>
                    <button type="button" onclick="applyDocFilter()" class="px-4 py-1.5 rounded-lg bg-slate-100 text-slate-700 text-sm hover:bg-slate-200">筛选</button>
                    <button type="button" onclick="location.href=\'/docs\'" class="px-4 py-1.5 rounded-lg border border-slate-200 text-slate-600 text-sm hover:bg-slate-50">重置</button>
                </div>
                <p class="text-xs text-slate-500">使用模板: %s</p>
            </div>
            <table class="min-w-full text-sm">
                <thead><tr class="border-b border-slate-200 text-left text-slate-600 bg-slate-50"><th class="px-4 py-2.5">标题</th><th class="px-4 py-2.5 w-24">创建者</th><th class="px-4 py-2.5 w-36">更新时间</th><th class="px-4 py-2.5 w-28">操作</th></tr></thead>
                <tbody>%s</tbody>
            </table>
        </div>
    </div>
    <script>
    function applyDocFilter(){
        var p=document.getElementById("docProjectFilter").value, m=document.getElementById("docModFilter").value, c=document.getElementById("docCatFilter").value;
        var q=[];
        if(p) q.push("project_id="+encodeURIComponent(p));
        if(m) q.push("module="+encodeURIComponent(m));
        if(c) q.push("category="+encodeURIComponent(c));
        location.href="/docs"+(q.length?("?"+q.join("&")):"");
    }
    function filterRows(){
        var q=(document.getElementById("docSearch").value||"").toLowerCase().trim();
        document.querySelectorAll(".doc-row").forEach(function(tr){
            var title=(tr.getAttribute("data-title")||"").toLowerCase();
            var creator=(tr.getAttribute("data-creator")||"").toLowerCase();
            var tags=(tr.getAttribute("data-tags")||"").toLowerCase();
            var show=!q||title.indexOf(q)>=0||creator.indexOf(q)>=0||tags.indexOf(q)>=0;
            tr.style.display=show?"":"none";
        });
    }
    if(document.getElementById("docSearch")) document.getElementById("docSearch").oninput=filterRows;
    document.querySelectorAll(".doc-del-btn").forEach(function(btn){ btn.onclick=function(){ if(!confirm("确定删除此文档？此操作不可恢复。")) return; var id=btn.getAttribute("data-id"); var h=_docH(); delete h["Content-Type"]; fetch("/docs/"+id, { method: "DELETE", headers: h, credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.reload(); }); }; });
    </script>
    ''' % (
        total, recent_count, my_count, att_count,
        ''.join(mod_cards),
        pinned_html,
        filter_project_opts,
        filter_mod_opts,
        filter_cat_opts,
        tpl_btns,
        rows_html
    )
    return _docs_layout(content, '文档中心', back_href='/admin', csrf_token=generate_csrf())


@bp.route('/docs/new')
@admin_required('docs')
def docs_new_page():
    template_id = (request.args.get('template') or '').strip()
    tpl = DOC_TEMPLATES.get(template_id) if template_id else None
    return _doc_edit_page(None, template=tpl)


@bp.route('/docs/<doc_id>')
@admin_required('docs')
def docs_view_page(doc_id):
    docs = _docs_db()
    doc = next((d for d in docs if d.get('id') == doc_id), None)
    if not doc:
        return '文档不存在', 404
    username = _current_username()
    if not _can_view(doc, username):
        return '无权限查看', 403
    can_edit_ = _can_edit(doc, username)
    can_manage_ = _can_manage(doc, username)
    can_del_ = _can_delete(doc, username)
    attachments = doc.get('attachments') or []
    att_rows = ''.join(
        '<tr><td class="px-4 py-2"><a href="/docs/%s/attachment/%s" class="text-blue-600 hover:underline">%s</a></td>'
        '<td class="px-4 py-2 text-sm text-gray-500">%s</td></tr>' % (
            html.escape(doc_id), html.escape(a.get('id', '')), html.escape(a.get('name', '')),
            a.get('uploaded_at', '')[:16] if a.get('uploaded_at') else ''
        )
        for a in attachments
    ) if attachments else '<tr><td colspan="2" class="px-4 py-4 text-gray-500">暂无附件</td></tr>'
    mod_badge = '<span class="px-2 py-0.5 rounded text-xs bg-slate-100 text-slate-600">%s</span>' % html.escape(_module_label(doc.get('module')))
    cat_badge = '<span class="px-2 py-0.5 rounded text-xs bg-indigo-50 text-indigo-700">%s</span>' % html.escape(_category_label(doc.get('category')))
    tags_str = (doc.get('tags') or '') if isinstance(doc.get('tags'), str) else ','.join(doc.get('tags') or [])
    tags_html = ''.join('<span class="px-1.5 py-0.5 rounded text-xs bg-gray-100 text-gray-600">%s</span>' % html.escape(t.strip()) for t in (tags_str or '').split(',') if t.strip())
    content = '''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <div class="flex justify-between items-start mb-4">
            <div>
                <h1 class="text-xl font-bold text-gray-800">%s</h1>
                <div class="flex flex-wrap gap-1.5 mt-2">%s %s %s</div>
            </div>
            <div class="flex gap-2">
                %s
                <a href="/docs" class="text-gray-600 hover:underline text-sm">返回知识中心</a>
            </div>
        </div>
        <div class="text-xs text-slate-500 mb-4">创建者 %s · 更新于 %s</div>
        <div class="prose max-w-none mb-6 doc-content bg-gray-50 rounded-lg p-6 text-gray-800 whitespace-pre-wrap">%s</div>
        <div class="border-t pt-4">
            <h3 class="font-semibold text-gray-800 mb-2">附件</h3>
            <table class="min-w-full text-sm"><tbody>%s</tbody></table>
        </div>
    </div>
    <script src="https://cdn.jsdelivr.net/npm/marked/marked.min.js"></script>
    <script>
    (function(){ var el=document.querySelector(".doc-content"); if(!el) return; var c=el.textContent; if(typeof marked!=="undefined"){ try{ el.innerHTML=marked.parse?marked.parse(c):marked(c); }catch(e){ el.innerHTML=c.replace(/</g,"&lt;"); } } else el.innerHTML=c.replace(/</g,"&lt;").replace(/>/g,"&gt;"); })();
    </script>
    ''' % (
        html.escape(doc.get('title') or '无标题'),
        mod_badge,
        cat_badge,
        tags_html,
        ('<a href="/docs/%s/edit" class="px-3 py-1.5 bg-indigo-600 text-white rounded text-sm hover:bg-indigo-700">编辑</a>' % html.escape(doc_id) if can_edit_ else '') +
        (' <a href="/docs/%s/permissions" class="px-3 py-1.5 border border-slate-200 rounded text-sm text-slate-700 hover:bg-slate-50">权限</a>' % html.escape(doc_id) if can_manage_ else '') +
        (' <button type="button" class="doc-del-view-btn px-3 py-1.5 border border-red-200 text-red-600 rounded text-sm hover:bg-red-50" data-id="%s">删除</button>' % html.escape(doc_id) if can_del_ else ''),
        html.escape(doc.get('created_by', '')),
        (doc.get('updated_at') or '')[:19] if doc.get('updated_at') else '-',
        html.escape(doc.get('content') or ''),
        att_rows
    )
    if can_del_:
        content += '<script>document.querySelector(".doc-del-view-btn").onclick=function(){ if(!confirm("确定删除此文档？此操作不可恢复。")) return; var h=_docH(); delete h["Content-Type"]; fetch("/docs/%s", { method: "DELETE", headers: h, credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.href="/docs"; }); };</script>' % html.escape(doc_id)
    return _docs_layout(content, doc.get('title') or '文档', back_href='/docs', csrf_token=generate_csrf())


@bp.route('/docs/<doc_id>/edit')
@admin_required('docs')
def docs_edit_page(doc_id):
    docs = _docs_db()
    doc = next((d for d in docs if d.get('id') == doc_id), None)
    if not doc:
        return '文档不存在', 404
    if not _can_edit(doc, _current_username()):
        return '无权限编辑', 403
    return _doc_edit_page(doc)


@bp.route('/docs/<doc_id>/permissions')
@admin_required('docs')
def docs_permissions_page(doc_id):
    docs = _docs_db()
    doc = next((d for d in docs if d.get('id') == doc_id), None)
    if not doc:
        return '文档不存在', 404
    if not _can_manage(doc, _current_username()):
        return '无权限管理', 403
    from models.data import users_db
    perms = doc.get('permissions') or {}
    editors = perms.get('editors') or []
    viewers = perms.get('viewers') or []
    user_opts = ''.join('<option value="%s">%s</option>' % (html.escape(u), html.escape(u)) for u in sorted(users_db.keys()) if u != doc.get('created_by'))
    content = '''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6 max-w-2xl">
        <h2 class="text-lg font-semibold text-gray-800 mb-4">文档权限</h2>
        <p class="text-sm text-gray-500 mb-4">创建者 %s 拥有全部权限。可为其他用户开通查看或编辑权限。</p>
        <form id="permForm" class="space-y-4">
            <div>
                <label class="block text-sm font-medium text-gray-700 mb-1">添加用户</label>
                <div class="flex gap-2">
                    <select name="user" class="px-3 py-2 border rounded text-sm flex-1">%s</select>
                    <select name="role" class="px-3 py-2 border rounded text-sm w-24"><option value="viewer">查看</option><option value="editor">编辑</option></select>
                    <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded text-sm">添加</button>
                </div>
            </div>
        </form>
        <div class="mt-4 space-y-2">
            <p class="text-sm font-medium text-gray-700">编辑者：%s</p>
            <p class="text-sm font-medium text-gray-700">查看者：%s</p>
        </div>
        <div class="mt-4"><a href="/docs/%s" class="text-blue-600 hover:underline">返回文档</a></div>
    </div>
    <script>
    document.getElementById("permForm").onsubmit=function(e){ e.preventDefault(); var u=this.user.value, r=this.role.value;
    fetch("/docs/%s/permissions", { method: "POST", headers: _docH(), body: JSON.stringify({ user: u, role: r }), credentials: "same-origin" })
    .then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.reload(); }); };
    </script>
    ''' % (
        html.escape(doc.get('created_by', '')),
        user_opts,
        ', '.join(editors) if editors else '无',
        ', '.join(viewers) if viewers else '无',
        html.escape(doc_id),
        html.escape(doc_id)
    )
    return _docs_layout(content, '权限设置', back_href='/docs/%s' % doc_id, csrf_token=generate_csrf())


def _doc_edit_page(doc, template=None):
    doc_id = doc.get('id') if doc else ''
    if template:
        title = template.get('title', '')
        content = template.get('content', '')
        module = template.get('module', '')
        category = template.get('category', '')
        project_id = ''
        tags = ''
        pinned = False
    else:
        if doc:
            title = (doc.get('title') or '')
            content = (doc.get('content') or '')
            module = doc.get('module', '')
            category = doc.get('category', '')
            project_id = resolve_project_id(doc.get('project_id')) or str(doc.get('project_id') or '')
            raw_tags = doc.get('tags')
            if isinstance(raw_tags, str):
                tags = raw_tags
            else:
                tags = ','.join(raw_tags or [])
            pinned = bool(doc.get('pinned'))
        else:
            title = ''
            content = ''
            module = ''
            category = ''
            project_id = resolve_project_id(request.args.get('project_id')) or ''
            tags = ''
            pinned = False
    att_list = ''
    if doc and doc.get('attachments'):
        att_list = ''.join('<span class="inline-flex items-center gap-1 mr-2 mb-1 px-2 py-1 bg-gray-100 rounded text-xs">%s <a href="#" class="doc-del-att text-red-500" data-id="%s">×</a></span>' % (html.escape(a.get('name', '')), html.escape(a.get('id', ''))) for a in doc.get('attachments', []))
    mod_opts = ''.join('<option value="%s"%s>%s</option>' % (mid, ' selected' if module == mid else '', html.escape(mname)) for mid, mname in [('', '-- 选择模块 --')] + list(DOC_MODULES))
    cat_opts = ''.join('<option value="%s"%s>%s</option>' % (cid, ' selected' if category == cid else '', html.escape(cname)) for cid, cname in [('', '-- 选择分类 --')] + list(DOC_CATEGORIES))
    project_opts = ''.join('<option value="%s"%s>%s</option>' % (html.escape(project['id']), ' selected' if project_id == project['id'] else '', html.escape(project['name'])) for project in ([{'id': '', 'name': '-- 閫夋嫨椤圭洰 --'}] + _project_choices(project_id)))
    html_content = '''
    <div class="bg-white rounded-xl shadow-sm border border-gray-100 p-6">
        <form id="docForm">
            <div class="grid grid-cols-1 md:grid-cols-4 gap-4 mb-4">
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">所属项目</label>
                    <select name="project_id" class="w-full px-4 py-2 border rounded-lg text-sm">%s</select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">所属模块</label>
                    <select name="module" class="w-full px-4 py-2 border rounded-lg text-sm">%s</select>
                </div>
                <div>
                    <label class="block text-sm font-medium text-gray-700 mb-1">文档分类</label>
                    <select name="category" class="w-full px-4 py-2 border rounded-lg text-sm">%s</select>
                </div>
                <div class="flex items-end gap-2">
                    <label class="flex items-center gap-2 cursor-pointer">
                        <input type="checkbox" name="pinned" %s class="rounded border-slate-300">
                        <span class="text-sm text-gray-700">置顶推荐</span>
                    </label>
                </div>
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-1">标签（逗号分隔）</label>
                <input type="text" name="tags" value="%s" class="w-full px-4 py-2 border rounded-lg text-sm" placeholder="如：权限, 审批, Jenkins">
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-1">标题</label>
                <input type="text" name="title" value="%s" class="w-full px-4 py-2 border rounded-lg text-sm" required>
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-1">内容（支持 Markdown）</label>
                <textarea name="content" rows="15" class="w-full px-4 py-2 border rounded-lg text-sm font-mono">%s</textarea>
            </div>
            <div class="mb-4">
                <label class="block text-sm font-medium text-gray-700 mb-1">附件</label>
                <div id="docAttList" class="mb-2">%s</div>
                <input type="file" id="docAttInput" multiple class="text-sm">
            </div>
            <div class="flex gap-2">
                <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium">保存</button>
                <a href="/docs" class="px-4 py-2 border border-gray-200 rounded-lg text-sm text-gray-700 hover:bg-gray-50">取消</a>
            </div>
        </form>
    </div>
    <script>
    var _docId = %s;
    var _docAtts = %s;
    document.getElementById("docForm").onsubmit=function(e){ e.preventDefault();
    var f=document.getElementById("docForm");
    var tagsVal=(f.tags.value||"").split(",").map(function(t){ return t.trim(); }).filter(Boolean).join(",");
    var d={ title: f.title.value.trim(), content: f.content.value, attachments: _docAtts, project_id: f.project_id.value, module: f.module.value, category: f.category.value, tags: tagsVal, pinned: !!f.pinned.checked };
    var url="/docs", method="POST";
    if(_docId){ url="/docs/"+_docId; method="PUT"; }
    fetch(url, { method: method, headers: _docH(), body: JSON.stringify(d), credentials: "same-origin" })
    .then(function(r){ return r.json(); }).then(function(x){ if(x.error) alert(x.error); else location.href="/docs/"+x.id; });
    };
    document.getElementById("docAttInput").onchange=function(){ var f=this.files; if(!f||!f.length) return; var tk=document.querySelector("meta[name=csrf-token]"); var tok=tk?tk.content:"";
    for(var i=0;i<f.length;i++){ (function(file){ var fd=new FormData(); fd.append("file", file); fd.append("doc_id", _docId||""); if(tok) fd.append("csrf_token", tok); fetch("/docs/upload", { method: "POST", body: fd, credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(x){ if(x.id){ _docAtts.push({ id: x.id, name: x.name, path: x.path||x.id }); var s=document.getElementById("docAttList"); s.innerHTML=s.innerHTML+('<span class=\\"inline-flex items-center gap-1 mr-2 mb-1 px-2 py-1 bg-gray-100 rounded text-xs\\">'+x.name+' <a href=\\"#\\" class=\\"doc-del-att text-red-500\\" data-id=\\"'+x.id+'\\">×</a></span>'); } else alert(x.error); }); })(f[i]); } this.value=""; };
    document.getElementById("docAttList").addEventListener("click", function(e){ var t=e.target; if(t.classList&&t.classList.contains("doc-del-att")){ e.preventDefault(); var id=t.getAttribute("data-id"); _docAtts=_docAtts.filter(function(a){ return a.id!==id; }); t.closest("span").remove(); } });
    </script>
    ''' % (
        project_opts,
        mod_opts,
        cat_opts,
        'checked' if pinned else '',
        html.escape(tags),
        html.escape(title),
        html.escape(content),
        att_list,
        ('"%s"' % html.escape(doc_id)) if doc_id else 'null',
        json_module.dumps(doc.get('attachments', []) if doc else [])
    )
    return _docs_layout(html_content, '编辑文档' if doc else '新建文档', back_href='/docs', csrf_token=generate_csrf())


def _docs_layout(content, title, back_href='/admin', csrf_token=''):
    csrf_meta = '<meta name="csrf-token" content="%s">' % html.escape(csrf_token) if csrf_token else ''
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    ''' + csrf_meta + '''
    <title>%s - 知识中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <script>
    function _docH(){ var m=document.querySelector("meta[name=csrf-token]"); return m&&m.content?{"X-CSRFToken":m.content,"Content-Type":"application/json"}:{"Content-Type":"application/json"}; }
    </script>
</head>
<body class="bg-slate-50 min-h-screen">
    <div class="max-w-6xl mx-auto px-4 py-6">
        <div class="flex justify-between items-center mb-6">
            <div class="flex items-center gap-3">
                <a href="/docs" class="text-indigo-600 hover:text-indigo-700 font-medium">知识中心</a>
                <span class="text-slate-300">/</span>
                <h1 class="text-xl font-bold text-slate-800">%s</h1>
            </div>
            <a href="%s" class="inline-flex items-center gap-1.5 px-4 py-2 rounded-lg border border-slate-200 text-slate-600 text-sm hover:bg-white hover:border-slate-300"><i class="fas fa-arrow-left"></i> 返回</a>
        </div>
        %s
    </div>
</body>
</html>''' % (html.escape(title), html.escape(title), html.escape(back_href), content)


# ---------- API ----------
@bp.route('/docs', methods=['POST'])
@admin_required('docs')
def docs_create():
    username = _current_username()
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': '请输入标题'}), 400
    docs = _docs_db()
    doc_id = uuid.uuid4().hex[:16]
    atts = data.get('attachments') or []
    for a in atts:
        a.setdefault('uploaded_at', datetime.now().isoformat())
        a.setdefault('uploaded_by', username)
    tags_val = (data.get('tags') or '').strip()
    project_id = resolve_project_id((data.get('project_id') or '').strip()) or None
    doc = {
        'id': doc_id,
        'title': title[:200],
        'content': (data.get('content') or '')[:500000],
        'created_by': username,
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
        'permissions': {'editors': [], 'viewers': []},
        'attachments': atts,
        'project_id': project_id,
        'module': (data.get('module') or '').strip() or None,
        'category': (data.get('category') or '').strip() or None,
        'tags': tags_val[:500] if tags_val else '',
        'pinned': bool(data.get('pinned')),
    }
    docs.append(doc)
    _save_docs(docs)
    return jsonify({'ok': True, 'id': doc_id})


@bp.route('/docs/<doc_id>', methods=['DELETE'])
@admin_required('docs')
def docs_delete(doc_id):
    username = _current_username()
    docs = _docs_db()
    doc = next((d for d in docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify({'error': '文档不存在'}), 404
    if not _can_delete(doc, username):
        return jsonify({'error': '无权限删除'}), 403
    docs[:] = [d for d in docs if d.get('id') != doc_id]
    _save_docs(docs)
    return jsonify({'ok': True})


@bp.route('/docs/<doc_id>', methods=['PUT'])
@admin_required('docs')
def docs_update(doc_id):
    username = _current_username()
    docs = _docs_db()
    doc = next((d for d in docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify({'error': '文档不存在'}), 404
    if not _can_edit(doc, username):
        return jsonify({'error': '无权限编辑'}), 403
    data = request.get_json() or {}
    doc['title'] = (data.get('title') or doc.get('title') or '')[:200]
    doc['content'] = (data.get('content') or doc.get('content') or '')[:500000]
    doc['updated_at'] = datetime.now().isoformat()
    if 'attachments' in data:
        doc['attachments'] = data['attachments']
    if 'project_id' in data:
        doc['project_id'] = resolve_project_id((data.get('project_id') or '').strip()) or None
    if 'module' in data:
        doc['module'] = (data.get('module') or '').strip() or None
    if 'category' in data:
        doc['category'] = (data.get('category') or '').strip() or None
    if 'tags' in data:
        doc['tags'] = (data.get('tags') or '')[:500]
    if 'pinned' in data:
        doc['pinned'] = bool(data.get('pinned'))
    _save_docs(docs)
    return jsonify({'ok': True, 'id': doc_id})


@bp.route('/docs/upload', methods=['POST'])
@admin_required('docs')
def docs_upload():
    username = _current_username()
    doc_id = (request.form.get('doc_id') or '').strip()
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': '请选择文件'}), 400
    max_mb = getattr(Config, 'DOCS_MAX_ATTACHMENT_MB', 20)
    f.seek(0, 2)
    size = f.tell()
    f.seek(0)
    if size > max_mb * 1024 * 1024:
        return jsonify({'error': '文件不得超过 %d MB' % int(max_mb)}), 400
    fn = secure_filename(f.filename)
    if not fn:
        fn = 'file_' + uuid.uuid4().hex[:8]
    att_dir = _attachments_dir()
    att_id = uuid.uuid4().hex[:16]
    ext = os.path.splitext(fn)[1]
    save_name = att_id + ext
    fp = os.path.join(att_dir, save_name)
    try:
        f.save(fp)
    except Exception as e:
        return jsonify({'error': str(e)}), 500
    att_info = {'id': att_id, 'name': fn, 'path': save_name, 'uploaded_at': datetime.now().isoformat(), 'uploaded_by': username}
    if doc_id:
        docs = _docs_db()
        doc = next((d for d in docs if d.get('id') == doc_id), None)
        if doc and _can_edit(doc, username):
            doc.setdefault('attachments', []).append(att_info)
            doc['updated_at'] = datetime.now().isoformat()
            _save_docs(docs)
    return jsonify({'ok': True, 'id': att_id, 'name': fn, 'path': save_name})


@bp.route('/docs/<doc_id>/attachment/<att_id>')
@admin_required('docs')
def docs_get_attachment(doc_id, att_id):
    docs = _docs_db()
    doc = next((d for d in docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify({'error': '文档不存在'}), 404
    if not _can_view(doc, _current_username()):
        return jsonify({'error': '无权限'}), 403
    att = next((a for a in (doc.get('attachments') or []) if a.get('id') == att_id), None)
    if not att:
        return jsonify({'error': '附件不存在'}), 404
    fp = os.path.join(_attachments_dir(), att.get('path', att_id))
    if not os.path.isfile(fp):
        return jsonify({'error': '文件已丢失'}), 404
    return send_file(fp, as_attachment=True, download_name=att.get('name', att_id))


@bp.route('/docs/<doc_id>/permissions', methods=['POST'])
@admin_required('docs')
def docs_set_permissions(doc_id):
    username = _current_username()
    docs = _docs_db()
    doc = next((d for d in docs if d.get('id') == doc_id), None)
    if not doc:
        return jsonify({'error': '文档不存在'}), 404
    if not _can_manage(doc, username):
        return jsonify({'error': '无权限'}), 403
    data = request.get_json() or {}
    user = (data.get('user') or '').strip()
    role = (data.get('role') or 'viewer').strip().lower()
    if not user:
        return jsonify({'error': '请选择用户'}), 400
    if user == doc.get('created_by'):
        return jsonify({'error': '创建者已有全部权限'}), 400
    if role not in ('viewer', 'editor'):
        role = 'viewer'
    perms = doc.setdefault('permissions', {'editors': [], 'viewers': []})
    for k in ('editors', 'viewers'):
        perms[k] = [u for u in (perms.get(k) or []) if u != user]
    if role == 'editor':
        perms.setdefault('editors', []).append(user)
    else:
        perms.setdefault('viewers', []).append(user)
    doc['updated_at'] = datetime.now().isoformat()
    _save_docs(docs)
    return jsonify({'ok': True})
