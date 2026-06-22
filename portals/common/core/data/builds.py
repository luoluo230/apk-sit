# -*- coding: utf-8 -*-
"""Build records and Jenkins instances."""

from datetime import datetime

from data._store import BUILD_VERSION_RECORDS_FILE, JENKINS_INSTANCES_FILE, load_document, save_document


def load_jenkins_instances():
    """返回 Jenkins 实例列表 [{id, port, status, pid, jenkins_home, added_at, added_by, started_at, started_by}, ...]"""
    raw = load_document(JENKINS_INSTANCES_FILE, [])
    return raw if isinstance(raw, list) else []


def save_jenkins_instances(instances):
    save_document(JENKINS_INSTANCES_FILE, instances)


def record_build_version(instance_id, build_number, version_id, project_id):
    """记录构建号与版本的关联，用于版本构建历史展示。"""
    records = load_document(BUILD_VERSION_RECORDS_FILE, [])
    if not isinstance(records, list):
        records = []
    records.append({
        'instance_id': instance_id or '',
        'build_number': int(build_number),
        'version_id': version_id or '',
        'project_id': project_id or '',
        'created_at': datetime.now().isoformat(),
    })
    # 只保留最近 500 条
    if len(records) > 500:
        records = records[-500:]
    save_document(BUILD_VERSION_RECORDS_FILE, records)


def get_build_records_for_version(version_id, instance_id=None):
    """获取某版本关联的构建记录，可选按实例筛选。返回按 build_number 降序。"""
    records = load_document(BUILD_VERSION_RECORDS_FILE, [])
    if not isinstance(records, list):
        return []
    vid = (version_id or '').strip()
    out = [r for r in records if (r.get('version_id') or '') == vid]
    if instance_id:
        iid = (instance_id or '').strip()
        out = [r for r in out if (r.get('instance_id') or '') == iid]
    out.sort(key=lambda x: x.get('build_number', 0), reverse=True)
    return out[:20]
