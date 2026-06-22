# -*- coding: utf-8 -*-
"""Download statistics and event tracking."""

from datetime import datetime, timedelta

from data._store import (
    DOWNLOAD_EVENTS_FILE,
    DOWNLOAD_EVENTS_MAX_DAYS,
    STATS_FILE,
    get_logger,
    load_document,
    save_document,
)

download_stats = load_document(STATS_FILE, {})


def save_stats():
    save_document(STATS_FILE, download_stats)


def load_download_events():
    raw = load_document(DOWNLOAD_EVENTS_FILE, [])
    if not isinstance(raw, list):
        return []
    cutoff = (datetime.now() - timedelta(days=DOWNLOAD_EVENTS_MAX_DAYS)).strftime('%Y-%m-%d')
    return [e for e in raw if isinstance(e, dict) and e.get('date', '') >= cutoff]


def save_download_events(events):
    cutoff = (datetime.now() - timedelta(days=DOWNLOAD_EVENTS_MAX_DAYS)).strftime('%Y-%m-%d')
    trimmed = [e for e in events if isinstance(e, dict) and e.get('date', '') >= cutoff]
    save_document(DOWNLOAD_EVENTS_FILE, trimmed)


def record_download_event(filename, source=None, ip=None):
    try:
        events = load_download_events()
        e = {'filename': filename, 'date': datetime.now().strftime('%Y-%m-%d')}
        if source:
            e['source'] = source
        if ip:
            e['ip'] = ip
        events.append(e)
        save_download_events(events)
    except Exception as ex:
        get_logger().warning("记录下载事件失败: %s", ex)


def get_total_downloads():
    return sum(download_stats.values())
