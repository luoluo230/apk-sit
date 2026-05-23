# -*- coding: utf-8 -*-
"""i18n 占位：文案翻译基础（商业级扩展预留）"""

import os
import json

_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_TRANSLATIONS_DIR = os.path.join(_ROOT, 'translations')
_CACHE = {}


def _load_messages(lang='zh_CN'):
    if lang in _CACHE:
        return _CACHE[lang]
    path = os.path.join(_TRANSLATIONS_DIR, lang, 'messages.json')
    if not os.path.isfile(path):
        _CACHE[lang] = {}
        return _CACHE[lang]
    try:
        with open(path, 'r', encoding='utf-8') as f:
            _CACHE[lang] = json.load(f)
    except Exception:
        _CACHE[lang] = {}
    return _CACHE[lang]


def _get_nested(data, key):
    """key 格式: common.home -> data['common']['home']"""
    parts = key.split('.')
    for p in parts:
        if isinstance(data, dict) and p in data:
            data = data[p]
        else:
            return None
    return data


def t(key, lang='zh_CN', default=None):
    """
    获取翻译文案。
    用法：t('common.home') -> '首页'
    key 支持嵌套：common.home, error.404_title
    """
    msg = _load_messages(lang)
    val = _get_nested(msg, key)
    if val is not None:
        return val
    return default if default is not None else key
