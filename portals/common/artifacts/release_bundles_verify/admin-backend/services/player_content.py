# -*- coding: utf-8 -*-
"""玩家侧内容：新闻、福利、论坛。"""

import os
import uuid
from datetime import datetime, timedelta

from flask import request, session

from config import DATA_DIR
from models.data import products_db, resolve_project_id, resolve_project_id_for_product, users_db
from services.media_library import normalize_local_media_url, normalize_local_media_urls
from utils import load_json, save_json

PLAYER_NEWS_FILE = os.path.join(DATA_DIR, 'player_news.json')
PLAYER_WELFARE_FILE = os.path.join(DATA_DIR, 'player_welfare.json')
FORUM_CATEGORIES_FILE = os.path.join(DATA_DIR, 'forum_categories.json')
FORUM_POSTS_FILE = os.path.join(DATA_DIR, 'forum_posts.json')
PLAYER_MODERATION_FILE = os.path.join(DATA_DIR, 'player_moderation.json')

DEFAULT_CATEGORIES = [
    {'id': 'general', 'name': '综合讨论', 'description': '日常交流、闲聊与版本印象'},
    {'id': 'strategy', 'name': '攻略技巧', 'description': '阵容、玩法与进阶心得'},
    {'id': 'event', 'name': '活动福利', 'description': '活动、礼包、兑换码与奖励'},
    {'id': 'feedback', 'name': '问题反馈', 'description': 'Bug、建议与优化意见'},
    {'id': 'fanart', 'name': '同人截图', 'description': '截图、创作与精彩瞬间'},
]

player_news_db = load_json(PLAYER_NEWS_FILE, [])
player_welfare_db = load_json(PLAYER_WELFARE_FILE, [])
forum_categories_db = load_json(FORUM_CATEGORIES_FILE, DEFAULT_CATEGORIES)
forum_posts_db = load_json(FORUM_POSTS_FILE, [])
player_moderation_db = load_json(PLAYER_MODERATION_FILE, {'players': {}})

if not forum_categories_db:
    forum_categories_db = list(DEFAULT_CATEGORIES)
    save_json(FORUM_CATEGORIES_FILE, forum_categories_db)


def _now():
    return datetime.now().isoformat()


def _publish_status(value, default='published'):
    allowed = {'draft', 'pending_approval', 'published', 'rejected', 'archived'}
    raw = (value or default or 'published').strip()
    return raw if raw in allowed else default


def _parse_media_urls(value):
    return normalize_local_media_urls(value, max_count=10)


def _resolve_content_project_id(data, fallback_product_id=''):
    direct_project_id = resolve_project_id((data.get('project_id') or '').strip())
    if direct_project_id:
        return direct_project_id
    product_id = (data.get('product_id') or fallback_product_id or '').strip()
    if not product_id:
        return ''
    product = next((item for item in products_db if isinstance(item, dict) and str(item.get('id') or '').strip() == product_id), None)
    return resolve_project_id_for_product(product) if product else ''


def _content_project_id(item):
    if not isinstance(item, dict):
        return ''
    project_id = resolve_project_id(item.get('project_id'))
    if project_id:
        return project_id
    return _resolve_content_project_id(item, item.get('product_id'))


def is_internal_creator(username=None):
    name = username or session.get('user') or ''
    if not name:
        return False
    return name in users_db and not (users_db.get(name) or {}).get('disabled')


def current_public_author():
    username = session.get('user') or ''
    if is_internal_creator(username):
        info = users_db.get(username) or {}
        role = (info.get('role') or 'user').strip()
        return {
            'display_name': username,
            'author_type': 'developer',
            'role': role,
            'is_official': role in ('super_admin', 'admin'),
        }
    return {
        'display_name': '游客玩家',
        'author_type': 'guest',
        'role': 'guest',
        'is_official': False,
    }


def save_player_news():
    save_json(PLAYER_NEWS_FILE, player_news_db)


def save_player_welfare():
    save_json(PLAYER_WELFARE_FILE, player_welfare_db)


def save_forum_posts():
    save_json(FORUM_POSTS_FILE, forum_posts_db)


def save_forum_categories():
    save_json(FORUM_CATEGORIES_FILE, forum_categories_db)


def save_player_moderation():
    save_json(PLAYER_MODERATION_FILE, player_moderation_db)


def current_author_key(username=None, display_name=''):
    username = username or session.get('user') or ''
    if is_internal_creator(username):
        return 'dev:' + username
    ip = (request.remote_addr or '0.0.0.0').strip()
    fallback_name = (display_name or 'guest').strip()[:30] or 'guest'
    return f'guest:{ip}:{fallback_name}'


def get_player_moderation(author_key):
    players = player_moderation_db.setdefault('players', {})
    if author_key not in players:
        players[author_key] = {
            'author_key': author_key,
            'display_name': '',
            'status': 'active',
            'muted_until': '',
            'banned_until': '',
            'notes': '',
            'updated_at': '',
        }
    return players[author_key]


def is_author_banned(author_key):
    info = get_player_moderation(author_key)
    banned_until = (info.get('banned_until') or '').strip()
    if not banned_until:
        return info.get('status') == 'banned'
    return banned_until > _now()


def is_author_muted(author_key):
    info = get_player_moderation(author_key)
    muted_until = (info.get('muted_until') or '').strip()
    if not muted_until:
        return info.get('status') == 'muted'
    return muted_until > _now()


def moderate_player(author_key, action, display_name='', note='', duration_hours=0):
    info = get_player_moderation(author_key)
    info['display_name'] = display_name or info.get('display_name') or author_key
    info['notes'] = (note or '').strip()[:300]
    info['updated_at'] = _now()
    if action == 'ban':
        info['status'] = 'banned'
        info['banned_until'] = (datetime.now() + timedelta(hours=max(0, int(duration_hours or 0)))).isoformat() if duration_hours else ''
    elif action == 'mute':
        info['status'] = 'muted'
        info['muted_until'] = (datetime.now() + timedelta(hours=max(1, int(duration_hours or 24)))).isoformat()
    elif action == 'unban':
        info['status'] = 'active'
        info['banned_until'] = ''
    elif action == 'unmute':
        info['status'] = 'active'
        info['muted_until'] = ''
    save_player_moderation()
    return info


def list_moderated_players():
    players = player_moderation_db.setdefault('players', {})
    rows = [value for value in players.values() if isinstance(value, dict)]
    rows.sort(key=lambda item: item.get('updated_at') or '', reverse=True)
    return rows


def moderate_post(post_id, action):
    post = get_forum_post(post_id)
    if not post:
        return None
    if action == 'hide':
        post['visible'] = False
    elif action == 'restore':
        post['visible'] = True
    elif action == 'pin':
        post['pinned'] = True
    elif action == 'unpin':
        post['pinned'] = False
    elif action == 'delete':
        post['deleted'] = True
        post['visible'] = False
    post['updated_at'] = _now()
    save_forum_posts()
    return post


def create_news_item(data, username=''):
    title = (data.get('title') or '').strip()[:120]
    if not title:
        return None
    media_urls = _parse_media_urls(data.get('media_urls') or data.get('images') or [])
    product_id = (data.get('product_id') or '').strip()
    item = {
        'id': uuid.uuid4().hex[:12],
        'kind': (data.get('kind') or '官方公告').strip()[:30],
        'title': title,
        'summary': (data.get('summary') or '').strip()[:300],
        'content': (data.get('content') or '').strip()[:5000],
        'video_url': normalize_local_media_url((data.get('video_url') or '').strip()[:300]),
        'media_urls': media_urls,
        'product_id': product_id,
        'project_id': _resolve_content_project_id(data, product_id),
        'pinned': bool(data.get('pinned')),
        'created_at': _now(),
        'updated_at': _now(),
        'published_at': _now() if _publish_status(data.get('publish_status')) == 'published' else '',
        'created_by': username or session.get('user') or '',
        'approval_id': (data.get('approval_id') or '').strip()[:40],
        'publish_status': _publish_status(data.get('publish_status')),
    }
    player_news_db.append(item)
    save_player_news()
    return item


def create_welfare_item(data, username=''):
    title = (data.get('title') or '').strip()[:120]
    if not title:
        return None
    media_urls = _parse_media_urls(data.get('media_urls') or data.get('images') or [])
    product_id = (data.get('product_id') or '').strip()
    item = {
        'id': uuid.uuid4().hex[:12],
        'title': title,
        'description': (data.get('description') or '').strip()[:500],
        'redeem_code': (data.get('redeem_code') or '').strip()[:80],
        'valid_until': (data.get('valid_until') or '').strip()[:40],
        'status': (data.get('status') or '进行中').strip()[:20],
        'video_url': normalize_local_media_url((data.get('video_url') or '').strip()[:300]),
        'media_urls': media_urls,
        'product_id': product_id,
        'project_id': _resolve_content_project_id(data, product_id),
        'created_at': _now(),
        'updated_at': _now(),
        'published_at': _now() if _publish_status(data.get('publish_status')) == 'published' else '',
        'created_by': username or session.get('user') or '',
        'approval_id': (data.get('approval_id') or '').strip()[:40],
        'publish_status': _publish_status(data.get('publish_status')),
    }
    player_welfare_db.append(item)
    save_player_welfare()
    return item


def get_latest_news(product_id=None, project_id=None, limit=6):
    rows = [
        item for item in player_news_db
        if isinstance(item, dict) and _publish_status(item.get('publish_status')) == 'published'
    ]
    if project_id:
        rows = [item for item in rows if _content_project_id(item) == project_id]
    if product_id:
        rows = [item for item in rows if item.get('product_id') == product_id]
    rows.sort(key=lambda item: (not item.get('pinned'), item.get('published_at') or item.get('created_at') or ''), reverse=False)
    rows.sort(key=lambda item: item.get('published_at') or item.get('created_at') or '', reverse=True)
    return rows[:limit]


def get_active_welfare(product_id=None, project_id=None, limit=8):
    rows = [
        item for item in player_welfare_db
        if isinstance(item, dict) and _publish_status(item.get('publish_status')) == 'published'
    ]
    if project_id:
        rows = [item for item in rows if _content_project_id(item) == project_id]
    if product_id:
        rows = [item for item in rows if item.get('product_id') == product_id]
    rows.sort(key=lambda item: item.get('published_at') or item.get('created_at') or '', reverse=True)
    return rows[:limit]


def get_forum_posts(product_id=None, project_id=None, category_id=None, limit=30):
    rows = [
        item for item in forum_posts_db
        if (
            isinstance(item, dict)
            and not item.get('deleted')
            and item.get('visible', True)
            and _publish_status(item.get('publish_status')) == 'published'
        )
    ]
    if project_id:
        rows = [item for item in rows if _content_project_id(item) == project_id]
    if product_id:
        rows = [item for item in rows if item.get('product_id') == product_id]
    if category_id:
        rows = [item for item in rows if (item.get('category_id') or '') == category_id]
    rows.sort(key=lambda item: (bool(item.get('pinned')), item.get('updated_at') or item.get('created_at') or ''), reverse=True)
    return rows[:limit]


def get_forum_post(post_id):
    for post in forum_posts_db:
        if isinstance(post, dict) and post.get('id') == post_id:
            return post
    return None


def create_forum_post(data, username=None):
    author = current_public_author() if username is None else current_public_author()
    title = (data.get('title') or '').strip()[:120]
    content = (data.get('content') or '').strip()[:5000]
    if not title or not content:
        return None
    if len(content) < 3:
        return None
    product_id = (data.get('product_id') or '').strip()[:80]
    project_id = _resolve_content_project_id(data, product_id)
    category_id = (data.get('category_id') or 'general').strip()[:40] or 'general'
    raw_media_urls = data.get('media_urls') or []
    if not isinstance(raw_media_urls, list):
        raw_media_urls = []
    display_name = (data.get('display_name') or '').strip()[:30]
    if author['author_type'] == 'guest':
        author['display_name'] = display_name or author['display_name']
    author_key = current_author_key(username, author['display_name'])
    if is_author_banned(author_key) or is_author_muted(author_key):
        return None
    post = {
        'id': uuid.uuid4().hex[:12],
        'title': title,
        'content': content,
        'product_id': product_id,
        'project_id': project_id,
        'category_id': category_id,
        'created_at': _now(),
        'updated_at': _now(),
        'published_at': _now() if _publish_status(data.get('publish_status')) == 'published' else '',
        'display_name': author['display_name'],
        'author_key': author_key,
        'author_type': author['author_type'],
        'role': author['role'],
        'is_official': author['is_official'],
        'pinned': bool(data.get('pinned')) and is_internal_creator(username),
        'visible': True,
        'deleted': False,
        'approval_id': (data.get('approval_id') or '').strip()[:40],
        'publish_status': _publish_status(data.get('publish_status')),
        'video_url': normalize_local_media_url((data.get('video_url') or '').strip()[:300]) if is_internal_creator(username) else '',
        'media_urls': normalize_local_media_urls(raw_media_urls, max_count=6) if is_internal_creator(username) else [],
        'comments': [],
    }
    profile = get_player_moderation(author_key)
    profile['display_name'] = author['display_name']
    profile['updated_at'] = _now()
    save_player_moderation()
    forum_posts_db.append(post)
    save_forum_posts()
    return post


def set_news_publish_state(item_id, publish_status, approval_id=None):
    target_status = _publish_status(publish_status)
    for item in player_news_db:
        if isinstance(item, dict) and item.get('id') == item_id:
            item['publish_status'] = target_status
            item['updated_at'] = _now()
            if approval_id is not None:
                item['approval_id'] = approval_id
            if target_status == 'published':
                item['published_at'] = item.get('published_at') or _now()
            save_player_news()
            return item
    return None


def set_welfare_publish_state(item_id, publish_status, approval_id=None):
    target_status = _publish_status(publish_status)
    for item in player_welfare_db:
        if isinstance(item, dict) and item.get('id') == item_id:
            item['publish_status'] = target_status
            item['updated_at'] = _now()
            if approval_id is not None:
                item['approval_id'] = approval_id
            if target_status == 'published':
                item['published_at'] = item.get('published_at') or _now()
            save_player_welfare()
            return item
    return None


def set_forum_post_publish_state(post_id, publish_status, approval_id=None):
    target_status = _publish_status(publish_status)
    for post in forum_posts_db:
        if isinstance(post, dict) and post.get('id') == post_id:
            post['publish_status'] = target_status
            post['updated_at'] = _now()
            if approval_id is not None:
                post['approval_id'] = approval_id
            if target_status == 'published':
                post['published_at'] = post.get('published_at') or _now()
            save_forum_posts()
            return post
    return None


def list_news_items(product_id=None, project_id=None, include_unpublished=True):
    rows = [item for item in player_news_db if isinstance(item, dict)]
    if not include_unpublished:
        rows = [item for item in rows if _publish_status(item.get('publish_status')) == 'published']
    if project_id:
        rows = [item for item in rows if _content_project_id(item) == project_id]
    if product_id:
        rows = [item for item in rows if item.get('product_id') == product_id]
    rows.sort(key=lambda item: item.get('updated_at') or item.get('published_at') or item.get('created_at') or '', reverse=True)
    return rows


def list_welfare_items(product_id=None, project_id=None, include_unpublished=True):
    rows = [item for item in player_welfare_db if isinstance(item, dict)]
    if not include_unpublished:
        rows = [item for item in rows if _publish_status(item.get('publish_status')) == 'published']
    if project_id:
        rows = [item for item in rows if _content_project_id(item) == project_id]
    if product_id:
        rows = [item for item in rows if item.get('product_id') == product_id]
    rows.sort(key=lambda item: item.get('updated_at') or item.get('published_at') or item.get('created_at') or '', reverse=True)
    return rows


def list_forum_posts_for_admin(product_id=None, project_id=None):
    rows = [item for item in forum_posts_db if isinstance(item, dict)]
    if project_id:
        rows = [item for item in rows if _content_project_id(item) == project_id]
    if product_id:
        rows = [item for item in rows if item.get('product_id') == product_id]
    rows.sort(key=lambda item: item.get('updated_at') or item.get('created_at') or '', reverse=True)
    return rows


def update_news_item(item_id, data, reset_publish_status=None):
    for item in player_news_db:
        if isinstance(item, dict) and item.get('id') == item_id:
            title = (data.get('title') or item.get('title') or '').strip()[:120]
            if not title:
                return None
            item['title'] = title
            item['kind'] = (data.get('kind') or item.get('kind') or '官方公告').strip()[:30]
            item['summary'] = (data.get('summary') or '').strip()[:300]
            item['content'] = (data.get('content') or '').strip()[:5000]
            item['video_url'] = normalize_local_media_url((data.get('video_url') or item.get('video_url') or '').strip()[:300])
            if 'media_urls' in data or 'images' in data:
                item['media_urls'] = _parse_media_urls(data.get('media_urls') or data.get('images') or [])
            item['product_id'] = (data.get('product_id') or '').strip()
            item['project_id'] = _resolve_content_project_id(data, item.get('product_id'))
            item['pinned'] = bool(data.get('pinned'))
            item['updated_at'] = _now()
            item['approval_id'] = ''
            if reset_publish_status:
                item['publish_status'] = _publish_status(reset_publish_status, 'pending_approval')
                if item['publish_status'] != 'published':
                    item['published_at'] = ''
            save_player_news()
            return item
    return None


def update_welfare_item(item_id, data, reset_publish_status=None):
    for item in player_welfare_db:
        if isinstance(item, dict) and item.get('id') == item_id:
            title = (data.get('title') or item.get('title') or '').strip()[:120]
            if not title:
                return None
            item['title'] = title
            item['description'] = (data.get('description') or '').strip()[:500]
            item['redeem_code'] = (data.get('redeem_code') or '').strip()[:80]
            item['valid_until'] = (data.get('valid_until') or '').strip()[:40]
            item['status'] = (data.get('status') or item.get('status') or '进行中').strip()[:20]
            item['video_url'] = normalize_local_media_url((data.get('video_url') or item.get('video_url') or '').strip()[:300])
            if 'media_urls' in data or 'images' in data:
                item['media_urls'] = _parse_media_urls(data.get('media_urls') or data.get('images') or [])
            item['product_id'] = (data.get('product_id') or '').strip()
            item['project_id'] = _resolve_content_project_id(data, item.get('product_id'))
            item['updated_at'] = _now()
            item['approval_id'] = ''
            if reset_publish_status:
                item['publish_status'] = _publish_status(reset_publish_status, 'pending_approval')
                if item['publish_status'] != 'published':
                    item['published_at'] = ''
            save_player_welfare()
            return item
    return None


def update_forum_post_item(post_id, data, reset_publish_status=None):
    for post in forum_posts_db:
        if isinstance(post, dict) and post.get('id') == post_id:
            title = (data.get('title') or post.get('title') or '').strip()[:120]
            content = (data.get('content') or post.get('content') or '').strip()[:5000]
            if not title or not content:
                return None
            raw_media_urls = data.get('media_urls') or []
            if not isinstance(raw_media_urls, list):
                raw_media_urls = []
            post['title'] = title
            post['content'] = content
            post['product_id'] = (data.get('product_id') or '').strip()[:80]
            post['project_id'] = _resolve_content_project_id(data, post.get('product_id'))
            post['category_id'] = (data.get('category_id') or post.get('category_id') or 'general').strip()[:40] or 'general'
            post['pinned'] = bool(data.get('pinned'))
            post['video_url'] = normalize_local_media_url((data.get('video_url') or '').strip()[:300])
            post['media_urls'] = normalize_local_media_urls(raw_media_urls, max_count=6)
            post['updated_at'] = _now()
            post['approval_id'] = ''
            if reset_publish_status:
                post['publish_status'] = _publish_status(reset_publish_status, 'pending_approval')
                if post['publish_status'] != 'published':
                    post['published_at'] = ''
            save_forum_posts()
            return post
    return None


def archive_news_item(item_id):
    return set_news_publish_state(item_id, 'archived')


def archive_welfare_item(item_id):
    return set_welfare_publish_state(item_id, 'archived')


def archive_forum_post_item(post_id):
    return set_forum_post_publish_state(post_id, 'archived')


def add_forum_comment(post_id, data, username=None):
    post = get_forum_post(post_id)
    if not post:
        return None
    if _publish_status(post.get('publish_status')) != 'published':
        return None
    author = current_public_author() if username is None else current_public_author()
    content = (data.get('content') or '').strip()[:2000]
    if not content:
        return None
    if len(content) < 2:
        return None
    display_name = (data.get('display_name') or '').strip()[:30]
    if author['author_type'] == 'guest':
        author['display_name'] = display_name or author['display_name']
    author_key = current_author_key(username, author['display_name'])
    if is_author_banned(author_key) or is_author_muted(author_key):
        return None
    comment = {
        'id': uuid.uuid4().hex[:12],
        'parent_id': (data.get('parent_id') or '').strip()[:40],
        'content': content,
        'created_at': _now(),
        'display_name': author['display_name'],
        'author_key': author_key,
        'author_type': author['author_type'],
        'role': author['role'],
        'is_official': author['is_official'],
    }
    profile = get_player_moderation(author_key)
    profile['display_name'] = author['display_name']
    profile['updated_at'] = _now()
    save_player_moderation()
    post.setdefault('comments', []).append(comment)
    post['updated_at'] = _now()
    save_forum_posts()
    return comment
