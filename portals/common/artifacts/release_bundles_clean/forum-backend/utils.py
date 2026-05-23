# -*- coding: utf-8 -*-
"""APK 下载中心 - 通用工具"""

import os
import sys
import json
import logging
from datetime import datetime
from markupsafe import escape

from config import Config, DATA_DIR


def _json_document_key(filepath):
    root = os.path.dirname(DATA_DIR) or os.getcwd()
    try:
        rel = os.path.relpath(filepath, root)
    except ValueError:
        rel = os.path.basename(filepath)
    return rel.replace('\\', '/')


def html_escape(text):
    """安全地转义 HTML 特殊字符"""
    return str(escape(text))


def load_json(filepath, default=None):
    if default is None:
        default = {}
    use_sqlite = getattr(Config, 'USE_SQLITE', False) or str(os.getenv('USE_SQLITE') or '').lower() in ('true', '1', 'yes')
    import_on_miss = getattr(Config, 'SQLITE_IMPORT_JSON_ON_MISS', False) or str(
        os.getenv('SQLITE_IMPORT_JSON_ON_MISS') or ''
    ).lower() in ('true', '1', 'yes')
    if use_sqlite:
        try:
            from models.db import get_json_document, has_json_document, set_json_document
            key = _json_document_key(filepath)
            if has_json_document(key):
                data = get_json_document(key, default)
                if data is not None:
                    return data
            if import_on_miss and os.path.exists(filepath):
                data = None
                last_error = None
                for encoding in ('utf-8', 'utf-8-sig', 'gbk'):
                    try:
                        with open(filepath, 'r', encoding=encoding, errors='strict') as f:
                            data = json.load(f)
                        break
                    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                        last_error = exc
                        continue
                if data is None:
                    raise last_error or ValueError('unable to decode json')
                set_json_document(key, data)
                return data
            # SQLite is the runtime source of truth. Seed missing documents
            # into the database instead of falling back to filesystem reads/writes.
            set_json_document(key, default)
            return default
        except Exception:
            return default
    if os.path.exists(filepath):
        try:
            data = None
            last_error = None
            for encoding in ('utf-8', 'utf-8-sig', 'gbk'):
                try:
                    with open(filepath, 'r', encoding=encoding, errors='strict') as f:
                        data = json.load(f)
                    break
                except (json.JSONDecodeError, UnicodeDecodeError) as exc:
                    last_error = exc
                    continue
            if data is None:
                raise last_error or ValueError('unable to decode json')
            return data
        except (json.JSONDecodeError, IOError, OSError, UnicodeDecodeError, ValueError):
            return default
    return default


def save_json(filepath, data):
    use_sqlite = getattr(Config, 'USE_SQLITE', False) or str(os.getenv('USE_SQLITE') or '').lower() in ('true', '1', 'yes')
    if use_sqlite:
        try:
            from models.db import set_json_document
            set_json_document(_json_document_key(filepath), data)
        except Exception:
            pass
    if use_sqlite and not getattr(Config, 'SQLITE_MIRROR_JSON', False):
        return
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def setup_logging():
    """商业级：结构化日志格式（时间、级别、模块、消息）"""
    os.makedirs(Config.LOG_DIR, exist_ok=True)
    log_file = os.path.join(Config.LOG_DIR, f'app_{datetime.now().strftime("%Y%m%d")}.log')
    # 结构化格式：时间 | 级别 | 模块 | 消息
    fmt = '[%(asctime)s] %(levelname)s [%(name)s]: %(message)s'
    datefmt = '%Y-%m-%d %H:%M:%S'
    handlers = [logging.FileHandler(log_file, encoding='utf-8')]
    if getattr(sys, 'stdout', None) is not None:
        handlers.append(logging.StreamHandler(sys.stdout))
    logging.basicConfig(
        level=logging.INFO,
        format=fmt,
        datefmt=datefmt,
        handlers=handlers
    )
    return logging.getLogger(__name__)
