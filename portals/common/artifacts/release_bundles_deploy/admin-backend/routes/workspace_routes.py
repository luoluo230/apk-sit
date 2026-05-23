# -*- coding: utf-8 -*-
"""个人工作区：文件、图片、书签、账号密码（加密）"""

import os
import re
import html
import json
import base64
import hashlib
import uuid
from datetime import datetime
from functools import wraps

from flask import Blueprint, request, jsonify, session, send_file
from werkzeug.utils import secure_filename

try:
    from flask_wtf.csrf import generate_csrf
except ImportError:
    generate_csrf = lambda: ''

from config import Config, DATA_DIR
from utils import load_json, save_json

bp = Blueprint('workspace', __name__)

# 用户工作区数据路径
WORKSPACES_META_FILE = os.path.join(DATA_DIR, 'workspaces_meta.json')


def _workspace_base():
    """工作区根目录（绝对路径）"""
    base = getattr(Config, 'WORKSPACE_BASE_DIR', None)
    if not base:
        base = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data', 'workspaces')
    if not os.path.isabs(base):
        base = os.path.normpath(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), base))
    return base


def _user_dir(username):
    """用户工作区目录"""
    if not username or not re.match(r'^[a-zA-Z0-9_\-\.]+$', username):
        return None
    return os.path.join(_workspace_base(), username)


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user' not in session:
            return jsonify({'error': '请先登录'}), 401
        return f(*args, **kwargs)
    return decorated


def _current_username():
    return session.get('user') or ''


def _fernet_key():
    """从 SECRET_KEY 派生 Fernet 兼容的 32 字节 key"""
    from config import Config
    key = Config.get_secret_key() or 'default-secret-change-me'
    return base64.urlsafe_b64encode(hashlib.sha256(key.encode()).digest())


def _encrypt_password(plain):
    """加密密码，用于存储。需安装 cryptography: pip install cryptography"""
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_fernet_key())
        return f.encrypt(plain.encode('utf-8')).decode('ascii')
    except ImportError:
        raise ValueError('请先安装 cryptography: pip install cryptography')
    except Exception:
        return ''


def _decrypt_password(encrypted):
    """解密密码"""
    if not encrypted:
        return ''
    try:
        from cryptography.fernet import Fernet
        f = Fernet(_fernet_key())
        return f.decrypt(encrypted.encode('ascii')).decode('utf-8')
    except Exception:
        return ''


def _ensure_user_dir(username):
    d = _user_dir(username)
    if d:
        os.makedirs(d, exist_ok=True)
    return d


def _load_user_bookmarks(username):
    path = os.path.join(_user_dir(username) or '', 'bookmarks.json')
    return load_json(path, [])


def _save_user_bookmarks(username, data):
    d = _user_dir(username)
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'bookmarks.json')
    save_json(path, data)


def _load_user_credentials(username):
    path = os.path.join(_user_dir(username) or '', 'credentials.json')
    raw = load_json(path, [])
    out = []
    for item in raw:
        out.append({
            'id': item.get('id'),
            'title': item.get('title', ''),
            'url': item.get('url', ''),
            'username': item.get('username', ''),
            'password_enc': item.get('password_enc', ''),
            'remark': item.get('remark', ''),
            'created_at': item.get('created_at', ''),
        })
    return out


def _save_user_credentials(username, items):
    d = _user_dir(username)
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'credentials.json')
    save_json(path, items)


def _load_user_notes(username):
    path = os.path.join(_user_dir(username) or '', 'notes.json')
    return load_json(path, [])


def _save_user_notes(username, data):
    d = _user_dir(username)
    if not d:
        return
    os.makedirs(d, exist_ok=True)
    path = os.path.join(d, 'notes.json')
    save_json(path, data)


# ---------- 页面 ----------
@bp.route('/workspace')
@login_required
def workspace_page():
    username = _current_username()
    csrf = generate_csrf()
    return _layout(_workspace_content(username), csrf)


def _layout(content, csrf_token=''):
    return '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="csrf-token" content="''' + html.escape(csrf_token) + '''">
    <title>个人工作区 - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
    <style>
        .ws-card{ transition: all 0.2s; }
        .ws-card:hover{ box-shadow: 0 10px 40px -10px rgba(0,0,0,0.12); }
        .ws-tab-active{ background: linear-gradient(135deg,#4f46e5,#6366f1); color: white; }
        .ws-tab{ transition: all 0.2s; }
    </style>
</head>
<body class="bg-slate-50 min-h-screen">
    <div class="max-w-6xl mx-auto px-4 py-6">
        <div class="flex justify-between items-center mb-6 flex-wrap gap-4">
            <div>
                <h1 class="text-2xl font-bold text-slate-800 tracking-tight">个人工作区</h1>
                <p class="text-slate-500 text-sm mt-0.5">文件、笔记、书签、凭证 — 仅您可见</p>
            </div>
            <a href="/" class="inline-flex items-center gap-2 px-4 py-2 rounded-lg border border-slate-200 text-slate-700 hover:bg-white hover:shadow-sm transition">
                <i class="fas fa-arrow-left text-sm"></i> 返回首页
            </a>
        </div>
        ''' + content + '''
    </div>
    <script>
    function _wsCsrf(){ var m=document.querySelector('meta[name=csrf-token]'); return m&&m.content ? {'X-CSRFToken':m.content} : {}; }
    function _wsHeaders(){ return Object.assign({'Content-Type':'application/json'}, _wsCsrf()); }
    </script>
</body>
</html>'''


def _workspace_content(username):
    tab = request.args.get('tab', 'notes')
    files_html = _files_section(username)
    bookmarks_html = _bookmarks_section(username)
    credentials_html = _credentials_section(username)
    notes_html = _notes_section(username)

    tabs = [
        ('notes', '工作笔记', 'fa-sticky-note', notes_html),
        ('files', '文件与图片', 'fa-folder-open', files_html),
        ('bookmarks', '网站书签', 'fa-bookmark', bookmarks_html),
        ('credentials', '账号密码', 'fa-key', credentials_html),
    ]
    nav = ''.join(
        '<a href="/workspace?tab=%s" class="ws-tab px-4 py-2.5 rounded-xl text-sm font-medium %s">'
        '<i class="fas %s mr-2"></i>%s</a>' % (
            k, 'ws-tab-active shadow-md' if tab == k else 'bg-white/80 text-slate-600 hover:bg-white hover:shadow-sm border border-slate-200/80',
            icon, label
        )
        for k, label, icon, _ in tabs
    )
    body = next((b for tk, _, _, b in tabs if tk == tab), notes_html)
    return '<div class="flex gap-2 mb-6 flex-wrap">%s</div><div class="ws-card bg-white rounded-2xl shadow-sm border border-slate-100 overflow-hidden">%s</div>' % (nav, body)


def _files_section(username):
    d = _ensure_user_dir(username)
    files = []
    if d and os.path.isdir(d):
        for fn in os.listdir(d):
            if fn in ('bookmarks.json', 'credentials.json', 'notes.json'):
                continue
            fp = os.path.join(d, fn)
            if os.path.isfile(fp):
                size = os.path.getsize(fp)
                mtime = datetime.fromtimestamp(os.path.getmtime(fp)).strftime('%Y-%m-%d %H:%M')
                ext = os.path.splitext(fn)[1].lower()
                is_img = ext in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
                files.append({'name': fn, 'size': size, 'mtime': mtime, 'is_image': is_img})
    files.sort(key=lambda x: x['mtime'], reverse=True)

    rows = ''.join(
        '<tr class="border-b border-gray-100"><td class="px-4 py-3">'
        + ('<img src="/workspace/file/%s" class="w-12 h-12 object-cover rounded" alt="">' % html.escape(f['name']) if f.get('is_image') else '<i class="fas fa-file text-gray-400"></i>')
        + '</td><td class="px-4 py-3 font-medium">' + html.escape(f['name']) + '</td>'
        '<td class="px-4 py-3 text-sm text-gray-500">' + _fmt_size(f['size']) + '</td>'
        '<td class="px-4 py-3 text-sm text-gray-500">' + html.escape(f['mtime']) + '</td>'
        '<td class="px-4 py-3"><a href="/workspace/file/' + html.escape(f['name']) + '" class="text-blue-600 hover:underline mr-2">下载</a>'
        '<button type="button" class="ws-del-file text-red-600 hover:underline" data-name="' + html.escape(f['name']) + '">删除</button></td></tr>'
        for f in files
    ) if files else '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500">暂无文件，可上传</td></tr>'

    return '''
    <h2 class="text-lg font-semibold text-gray-800 mb-4">我的文件</h2>
    <form id="wsUploadForm" class="mb-4 flex gap-2 items-center">
        <input type="file" id="wsFileInput" name="file" multiple class="text-sm">
        <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">上传</button>
    </form>
    <table class="min-w-full text-sm">
        <thead><tr class="border-b border-gray-200 text-left text-gray-600"><th class="px-4 py-2">预览</th><th class="px-4 py-2">文件名</th><th class="px-4 py-2">大小</th><th class="px-4 py-2">修改时间</th><th class="px-4 py-2">操作</th></tr></thead>
        <tbody>%s</tbody>
    </table>
    <script>
    document.getElementById("wsUploadForm").onsubmit=function(e){ e.preventDefault(); var inp=document.getElementById("wsFileInput"); if(!inp.files||!inp.files.length){ alert("请选择文件"); return; }
    var tk=document.querySelector("meta[name=csrf-token]"); var tok=tk?tk.content:"";
    for(var i=0;i<inp.files.length;i++){ (function(f){ var fd=new FormData(); fd.append("file", f); if(tok) fd.append("csrf_token", tok); fetch("/workspace/upload", { method: "POST", body: fd, credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.reload(); }); })(inp.files[i]); } inp.value=""; };
    document.querySelectorAll(".ws-del-file").forEach(function(btn){ btn.onclick=function(){ if(!confirm("确定删除？")) return; var n=btn.getAttribute("data-name"); fetch("/workspace/file/"+encodeURIComponent(n), { method: "DELETE", headers: _wsCsrf(), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.reload(); }); }; });
    </script>
    ''' % rows


def _fmt_size(n):
    if n < 1024:
        return str(n) + ' B'
    if n < 1024 * 1024:
        return '%.1f KB' % (n / 1024)
    return '%.1f MB' % (n / 1024 / 1024)


def _notes_section(username):
    """工作笔记：创建、编辑、删除"""
    items = _load_user_notes(username)
    items.sort(key=lambda x: x.get('updated_at', x.get('created_at', '')), reverse=True)
    cards = []
    for n in items:
        tid = html.escape(n.get('id', ''))
        title = html.escape((n.get('title') or '无标题')[:80])
        preview = html.escape((n.get('content') or '')[:120].replace('\n', ' '))
        updated = (n.get('updated_at') or n.get('created_at') or '')[:16]
        cards.append('''
        <div class="border border-slate-200 rounded-xl p-4 hover:border-indigo-200 hover:shadow-md transition group">
            <div class="flex justify-between items-start">
                <h3 class="font-semibold text-slate-800 truncate flex-1">''' + title + '''</h3>
                <div class="flex gap-1 opacity-0 group-hover:opacity-100 transition">
                    <a href="/workspace?tab=notes&edit=''' + tid + '''" class="px-2 py-1 text-xs text-indigo-600 hover:bg-indigo-50 rounded">编辑</a>
                    <button type="button" class="ws-del-note px-2 py-1 text-xs text-red-600 hover:bg-red-50 rounded" data-id="''' + tid + '''">删除</button>
                </div>
            </div>
            <p class="text-sm text-slate-500 mt-1 line-clamp-2">''' + preview + '''</p>
            <span class="text-xs text-slate-400 mt-2 block">''' + html.escape(updated) + '''</span>
        </div>''')
    cards_html = '<div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4">' + ''.join(cards) + '</div>' if cards else '<p class="text-slate-500 py-8 text-center">暂无工作笔记，点击右侧创建</p>'
    edit_id = request.args.get('edit', '')
    edit_note = next((n for n in items if n.get('id') == edit_id), None) if edit_id else None
    form_title = html.escape(edit_note.get('title', '') if edit_note else '')
    form_content = html.escape(edit_note.get('content', '') if edit_note else '')
    form_html = '''
    <div class="mb-6 p-5 bg-slate-50 rounded-xl border border-slate-200">
        <h3 class="font-medium text-slate-800 mb-3">''' + ('编辑笔记' if edit_note else '新建笔记') + '''</h3>
        <form id="wsNoteForm" class="space-y-3">
            <input type="hidden" name="id" value="''' + (html.escape(edit_id) if edit_id else '') + '''">
            <div><input type="text" name="title" placeholder="标题" value="''' + form_title + '''" class="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500" required></div>
            <div><textarea name="content" placeholder="内容（支持多行）" rows="4" class="w-full px-4 py-2.5 border border-slate-200 rounded-lg text-sm focus:ring-2 focus:ring-indigo-500 focus:border-indigo-500">''' + form_content + '''</textarea></div>
            <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700">''' + ('保存' if edit_note else '创建') + '''</button>
        </form>
    </div>
    '''
    return '''
    <div class="p-6">
        <div class="flex justify-between items-center mb-6">
            <h2 class="text-lg font-semibold text-slate-800">工作笔记</h2>
        </div>
        ''' + form_html + '''
        <h3 class="font-medium text-slate-700 mb-3 mt-6">我的笔记</h3>
        ''' + cards_html + '''
        <script>
        document.getElementById("wsNoteForm").onsubmit=function(e){ e.preventDefault(); var f=this; var d={ title: f.title.value.trim(), content: f.content.value }; if(!d.title){ alert("请输入标题"); return; } var id=f.querySelector("[name=id]").value; var url="/workspace/notes"; var method="POST"; if(id){ url="/workspace/notes/"+id; method="PUT"; d.id=id; }
        fetch(url, { method: method, headers: _wsHeaders(), body: JSON.stringify(d), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(x){ if(x.error) alert(x.error); else location.reload(); });
        };
        document.querySelectorAll(".ws-del-note").forEach(function(btn){ btn.onclick=function(){ if(!confirm("确定删除？")) return; fetch("/workspace/notes/"+encodeURIComponent(btn.getAttribute("data-id")), { method: "DELETE", headers: _wsCsrf(), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.reload(); }); }; });
        </script>
    </div>
    '''


def _bookmarks_section(username):
    items = _load_user_bookmarks(username)
    rows = ''.join(
        '<tr class="border-b border-gray-100"><td class="px-4 py-3"><a href="%s" target="_blank" class="text-blue-600 hover:underline">%s</a></td>'
        '<td class="px-4 py-3 text-sm text-gray-500">%s</td>'
        '<td class="px-4 py-3"><button type="button" class="ws-del-bookmark text-red-600 hover:underline" data-id="%s">删除</button></td></tr>' % (
            html.escape(item.get('url', '#')),
            html.escape((item.get('title') or item.get('url', ''))[:50]),
            html.escape((item.get('remark') or '')[:30]),
            html.escape(item.get('id', '')),
        )
        for item in items
    ) if items else '<tr><td colspan="3" class="px-4 py-8 text-center text-gray-500">暂无书签</td></tr>'

    return '''
    <h2 class="text-lg font-semibold text-gray-800 mb-4">网站书签</h2>
    <form id="wsBookmarkForm" class="mb-4 flex flex-wrap gap-2 items-end">
        <div><label class="block text-xs text-gray-500">标题</label><input type="text" name="title" placeholder="网站名称" class="px-3 py-2 border rounded text-sm w-40"></div>
        <div><label class="block text-xs text-gray-500">网址</label><input type="url" name="url" placeholder="https://..." class="px-3 py-2 border rounded text-sm w-64" required></div>
        <div><label class="block text-xs text-gray-500">备注</label><input type="text" name="remark" placeholder="可选" class="px-3 py-2 border rounded text-sm w-32"></div>
        <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm">添加</button>
    </form>
    <table class="min-w-full text-sm">
        <thead><tr class="border-b border-gray-200 text-left text-gray-600"><th class="px-4 py-2">标题/链接</th><th class="px-4 py-2">备注</th><th class="px-4 py-2">操作</th></tr></thead>
        <tbody>%s</tbody>
    </table>
    <script>
    document.getElementById("wsBookmarkForm").onsubmit=function(e){ e.preventDefault(); var f=this; var d={ title: f.title.value.trim(), url: f.url.value.trim(), remark: f.remark.value.trim() }; if(!d.url){ alert("请填写网址"); return; }
    fetch("/workspace/bookmarks", { method: "POST", headers: _wsHeaders(), body: JSON.stringify(d), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(x){ if(x.error) alert(x.error); else location.reload(); }); };
    document.querySelectorAll(".ws-del-bookmark").forEach(function(btn){ btn.onclick=function(){ if(!confirm("确定删除？")) return; fetch("/workspace/bookmarks/"+encodeURIComponent(btn.getAttribute("data-id")), { method: "DELETE", headers: _wsCsrf(), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.reload(); }); }; });
    </script>
    ''' % rows


def _credentials_section(username):
    items = _load_user_credentials(username)
    rows = ''.join(
        '<tr class="border-b border-gray-100"><td class="px-4 py-3 font-medium">%s</td><td class="px-4 py-3 text-sm">%s</td>'
        '<td class="px-4 py-3"><span class="text-gray-400">••••••••</span> <button type="button" class="ws-show-pwd text-blue-600 text-xs ml-1" data-id="%s">显示</button></td>'
        '<td class="px-4 py-3 text-sm text-gray-500">%s</td>'
        '<td class="px-4 py-3"><button type="button" class="ws-del-cred text-red-600 hover:underline text-xs" data-id="%s">删除</button></td></tr>' % (
            html.escape(item.get('title', '')[:30]),
            html.escape(item.get('username', '')[:20]),
            html.escape(item.get('id', '')),
            html.escape((item.get('remark') or '')[:20]),
            html.escape(item.get('id', '')),
        )
        for item in items
    ) if items else '<tr><td colspan="5" class="px-4 py-8 text-center text-gray-500">暂无记录</td></tr>'

    return '''
    <h2 class="text-lg font-semibold text-gray-800 mb-4">账号密码</h2>
    <p class="text-sm text-gray-500 mb-4">密码加密存储，仅您本人可查看。</p>
    <form id="wsCredForm" class="mb-4 flex flex-wrap gap-2 items-end">
        <div><label class="block text-xs text-gray-500">名称</label><input type="text" name="title" placeholder="如：公司邮箱" class="px-3 py-2 border rounded text-sm w-36" required></div>
        <div><label class="block text-xs text-gray-500">网址</label><input type="url" name="url" placeholder="可选" class="px-3 py-2 border rounded text-sm w-48"></div>
        <div><label class="block text-xs text-gray-500">账号</label><input type="text" name="username" placeholder="用户名" class="px-3 py-2 border rounded text-sm w-32"></div>
        <div><label class="block text-xs text-gray-500">密码</label><input type="password" name="password" placeholder="密码" class="px-3 py-2 border rounded text-sm w-32"></div>
        <div><label class="block text-xs text-gray-500">备注</label><input type="text" name="remark" placeholder="可选" class="px-3 py-2 border rounded text-sm w-24"></div>
        <button type="submit" class="px-4 py-2 bg-indigo-600 text-white rounded-lg text-sm">添加</button>
    </form>
    <table class="min-w-full text-sm">
        <thead><tr class="border-b border-gray-200 text-left text-gray-600"><th class="px-4 py-2">名称</th><th class="px-4 py-2">账号</th><th class="px-4 py-2">密码</th><th class="px-4 py-2">备注</th><th class="px-4 py-2">操作</th></tr></thead>
        <tbody>%s</tbody>
    </table>
    <script>
    document.getElementById("wsCredForm").onsubmit=function(e){ e.preventDefault(); var f=this; var d={ title: f.title.value.trim(), url: f.url.value.trim(), username: f.username.value.trim(), password: f.password.value, remark: f.remark.value.trim() }; if(!d.title){ alert("请填写名称"); return; }
    fetch("/workspace/credentials", { method: "POST", headers: _wsHeaders(), body: JSON.stringify(d), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(x){ if(x.error) alert(x.error); else location.reload(); }); };
    document.querySelectorAll(".ws-show-pwd").forEach(function(btn){ btn.onclick=function(){ var id=btn.getAttribute("data-id"); fetch("/workspace/credentials/"+encodeURIComponent(id)+"/reveal", { credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.password){ var span=btn.previousElementSibling; span.textContent=d.password; span.classList.remove("text-gray-400"); btn.style.display="none"; } else alert(d.error||"获取失败"); }); }; });
    document.querySelectorAll(".ws-del-cred").forEach(function(btn){ btn.onclick=function(){ if(!confirm("确定删除？")) return; fetch("/workspace/credentials/"+encodeURIComponent(btn.getAttribute("data-id")), { method: "DELETE", headers: _wsCsrf(), credentials: "same-origin" }).then(function(r){ return r.json(); }).then(function(d){ if(d.error) alert(d.error); else location.reload(); }); }; });
    </script>
    ''' % rows


# ---------- API ----------
@bp.route('/workspace/upload', methods=['POST'])
@login_required
def workspace_upload():
    username = _current_username()
    d = _ensure_user_dir(username)
    if not d:
        return jsonify({'error': '工作区不可用'}), 500
    f = request.files.get('file')
    if not f or not f.filename:
        return jsonify({'error': '请选择文件'}), 400
    fn = secure_filename(f.filename)
    if not fn:
        fn = 'file_' + uuid.uuid4().hex[:8]
    fp = os.path.join(d, fn)
    try:
        f.save(fp)
        return jsonify({'ok': True, 'name': fn})
    except Exception as e:
        return jsonify({'error': str(e)}), 500


@bp.route('/workspace/file/<path:filename>', methods=['GET', 'HEAD', 'DELETE'])
@login_required
def workspace_file(filename):
    fn = secure_filename(os.path.basename(filename))
    username = _current_username()
    d = _user_dir(username)
    if not d:
        return jsonify({'error': '无权限'}), 403
    fp = os.path.join(d, fn)
    if not os.path.isfile(fp) or os.path.dirname(os.path.abspath(fp)) != os.path.abspath(d):
        return jsonify({'error': '文件不存在'}), 404
    if request.method == 'DELETE':
        if fn in ('bookmarks.json', 'credentials.json'):
            return jsonify({'error': '不能删除系统文件'}), 400
        try:
            os.remove(fp)
        except Exception as e:
            return jsonify({'error': str(e)}), 500
        return jsonify({'ok': True})
    ext = os.path.splitext(fn)[1].lower()
    as_attach = ext not in ('.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp')
    return send_file(fp, as_attachment=as_attach, download_name=fn)


# ---------- 书签 ----------
@bp.route('/workspace/bookmarks', methods=['POST'])
@login_required
def workspace_bookmarks_add():
    username = _current_username()
    data = request.get_json() or {}
    url = (data.get('url') or '').strip()
    if not url:
        return jsonify({'error': '请填写网址'}), 400
    items = _load_user_bookmarks(username)
    bid = uuid.uuid4().hex[:12]
    items.append({
        'id': bid,
        'title': (data.get('title') or url)[:100],
        'url': url[:500],
        'remark': (data.get('remark') or '')[:200],
        'created_at': datetime.now().isoformat(),
    })
    _save_user_bookmarks(username, items)
    return jsonify({'ok': True, 'id': bid})


@bp.route('/workspace/bookmarks/<bid>', methods=['DELETE'])
@login_required
def workspace_bookmarks_delete(bid):
    username = _current_username()
    items = [x for x in _load_user_bookmarks(username) if x.get('id') != bid]
    _save_user_bookmarks(username, items)
    return jsonify({'ok': True})


# ---------- 账号密码 ----------
@bp.route('/workspace/credentials', methods=['POST'])
@login_required
def workspace_credentials_add():
    username = _current_username()
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': '请填写名称'}), 400
    items = _load_user_credentials(username)
    cid = uuid.uuid4().hex[:12]
    pwd = (data.get('password') or '').strip()
    try:
        enc = _encrypt_password(pwd) if pwd else ''
    except ValueError as e:
        return jsonify({'error': str(e)}), 400
    items.append({
        'id': cid,
        'title': title[:80],
        'url': (data.get('url') or '')[:300],
        'username': (data.get('username') or '')[:100],
        'password_enc': enc,
        'remark': (data.get('remark') or '')[:200],
        'created_at': datetime.now().isoformat(),
    })
    _save_user_credentials(username, items)
    return jsonify({'ok': True, 'id': cid})


@bp.route('/workspace/credentials/<cid>', methods=['DELETE'])
@login_required
def workspace_credentials_delete(cid):
    username = _current_username()
    raw = load_json(os.path.join(_user_dir(username) or '', 'credentials.json'), [])
    items = [x for x in raw if x.get('id') != cid]
    _save_user_credentials(username, items)
    return jsonify({'ok': True})


# ---------- 工作笔记 ----------
@bp.route('/workspace/notes', methods=['POST'])
@login_required
def workspace_notes_add():
    username = _current_username()
    data = request.get_json() or {}
    title = (data.get('title') or '').strip()
    if not title:
        return jsonify({'error': '请输入标题'}), 400
    items = _load_user_notes(username)
    nid = uuid.uuid4().hex[:12]
    items.append({
        'id': nid,
        'title': title[:200],
        'content': (data.get('content') or '')[:50000],
        'created_at': datetime.now().isoformat(),
        'updated_at': datetime.now().isoformat(),
    })
    _save_user_notes(username, items)
    return jsonify({'ok': True, 'id': nid})


@bp.route('/workspace/notes/<nid>', methods=['PUT'])
@login_required
def workspace_notes_update(nid):
    username = _current_username()
    data = request.get_json() or {}
    items = _load_user_notes(username)
    note = next((n for n in items if n.get('id') == nid), None)
    if not note:
        return jsonify({'error': '笔记不存在'}), 404
    title = (data.get('title') or note.get('title') or '').strip()
    if not title:
        return jsonify({'error': '请输入标题'}), 400
    note['title'] = title[:200]
    note['content'] = (data.get('content', note.get('content')) or '')[:50000]
    note['updated_at'] = datetime.now().isoformat()
    _save_user_notes(username, items)
    return jsonify({'ok': True})


@bp.route('/workspace/notes/<nid>', methods=['DELETE'])
@login_required
def workspace_notes_delete(nid):
    username = _current_username()
    items = [n for n in _load_user_notes(username) if n.get('id') != nid]
    _save_user_notes(username, items)
    return jsonify({'ok': True})


@bp.route('/workspace/credentials/<cid>/reveal')
@login_required
def workspace_credentials_reveal(cid):
    username = _current_username()
    raw = load_json(os.path.join(_user_dir(username) or '', 'credentials.json'), [])
    item = next((x for x in raw if x.get('id') == cid), None)
    if not item:
        return jsonify({'error': '记录不存在'}), 404
    enc = item.get('password_enc', '')
    if not enc:
        return jsonify({'password': ''})
    try:
        plain = _decrypt_password(enc)
        return jsonify({'password': plain})
    except Exception:
        return jsonify({'error': '解密失败'}), 500
