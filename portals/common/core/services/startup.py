# -*- coding: utf-8 -*-
"""启动期服务：下载直链、局域网 IP、飞书告警、定时报表、后台调度"""

import os
import sys
import json
import socket
import logging
from datetime import datetime

from config import Config, JENKINS_CLONE_DIR

logger = logging.getLogger(__name__)


def _resolve_overlay_root():
    """Resolve jenkins overlay directory across converged layouts."""
    core_root = os.path.dirname(os.path.dirname(__file__))
    common_root = os.path.dirname(core_root)
    project_root = os.path.dirname(os.path.dirname(common_root))
    candidates = [
        os.path.join(core_root, 'jenkins-clone-overlay'),
        os.path.join(common_root, 'archives', 'jenkins-clone-overlay'),
        os.path.join(project_root, 'jenkins-clone-overlay'),
    ]
    for path in candidates:
        if os.path.isdir(path):
            return path
    return ''


def _is_private_ip(ip):
    if not ip or ip == '127.0.0.1':
        return False
    parts = ip.split('.')
    if len(parts) != 4:
        return False
    try:
        a, b = int(parts[0]), int(parts[1])
        if a == 192 and b == 168:
            return True
        if a == 10:
            return True
        if a == 172 and 16 <= b <= 31:
            return True
    except (ValueError, IndexError):
        pass
    return False


def get_lan_ip():
    """获取本机局域网 IP。"""
    candidates = []
    try:
        hostname = socket.gethostname()
        _, _, ipaddrlist = socket.gethostbyname_ex(hostname)
        candidates.extend(ipaddrlist or [])
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.settimeout(0.5)
        s.connect(('8.8.8.8', 80))
        candidates.append(s.getsockname()[0])
        s.close()
    except Exception:
        pass
    if sys.platform == 'darwin':
        try:
            import subprocess
            for iface in ('en0', 'en1', 'en2'):
                out = subprocess.run(
                    ['ipconfig', 'getifaddr', iface],
                    capture_output=True, text=True, timeout=1
                )
                if out.returncode == 0 and out.stdout and out.stdout.strip():
                    candidates.append(out.stdout.strip())
        except Exception:
            pass
    for ip in candidates:
        if ip and ip.startswith('192.168.'):
            return ip
    for ip in candidates:
        if _is_private_ip(ip):
            return ip
    for ip in candidates:
        if ip and ip != '127.0.0.1':
            return ip
    return '127.0.0.1'


def get_canonical_base_url():
    """与下载中心显示一致：http://<局域网IP>:<PORT>。"""
    return f"http://{get_lan_ip()}:{Config.PORT}"


def _send_feishu_alert(text):
    url = getattr(Config, 'ALERT_FEISHU_WEBHOOK', '') or os.getenv('ALERT_FEISHU_WEBHOOK', '').strip()
    if not url:
        return
    try:
        import urllib.request
        req = urllib.request.Request(
            url,
            data=json.dumps({'msg_type': 'text', 'content': {'text': text}}).encode(),
            method='POST',
            headers={'Content-Type': 'application/json'}
        )
        with urllib.request.urlopen(req, timeout=5) as r:
            pass
    except Exception as e:
        logger.warning("飞书告警发送失败: %s", e)


def _run_alert_check():
    try:
        import shutil
        if Config.ALERT_FEISHU_WEBHOOK and os.path.isdir(Config.APK_DIR):
            usage = shutil.disk_usage(Config.APK_DIR)
            free_gb = usage.free / (1024 ** 3)
            if free_gb < getattr(Config, 'DISK_ALERT_GB', 5):
                _send_feishu_alert(
                    "[APK 下载中心] 告警：存储空间不足，剩余 %.1f GB（阈值 %.1f GB）"
                    % (free_gb, getattr(Config, 'DISK_ALERT_GB', 5))
                )
    except Exception as e:
        logger.warning("告警检查失败: %s", e)


def _send_report_email():
    from models.data import download_stats, load_download_events
    if not Config.REPORT_EMAIL_TO or not Config.SMTP_HOST or not Config.SMTP_USER:
        return
    try:
        import smtplib
        from email.mime.text import MIMEText
        from email.mime.multipart import MIMEMultipart
        total = sum(download_stats.values())
        events = load_download_events()
        recent = len([e for e in events if e.get('date') == datetime.now().strftime('%Y-%m-%d')])
        body = "APK 下载中心 每日报表\n\n总下载量: %s\n今日下载: %s\n" % (total, recent)
        msg = MIMEMultipart()
        msg['Subject'] = "APK 下载中心 每日报表 " + datetime.now().strftime('%Y-%m-%d')
        msg.attach(MIMEText(body, 'plain', 'utf-8'))
        port = Config.SMTP_PORT or 587
        to_list = [e.strip() for e in Config.REPORT_EMAIL_TO.split(',') if e.strip()]
        if not to_list:
            return
        if port == 465:
            with smtplib.SMTP_SSL(Config.SMTP_HOST, port) as s:
                if Config.SMTP_USER and Config.SMTP_PASSWORD:
                    s.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                s.sendmail(Config.SMTP_USER or 'noreply@apk-site', to_list, msg.as_string())
        else:
            with smtplib.SMTP(Config.SMTP_HOST, port) as s:
                s.starttls()
                if Config.SMTP_USER and Config.SMTP_PASSWORD:
                    s.login(Config.SMTP_USER, Config.SMTP_PASSWORD)
                s.sendmail(Config.SMTP_USER or 'noreply@apk-site', to_list, msg.as_string())
    except Exception as e:
        logger.warning("报表邮件发送失败: %s", e)


def _run_scheduled_backup():
    """商业级：定时备份 + 保留策略。"""
    retain = int(os.getenv('BACKUP_RETENTION_COUNT', str(getattr(Config, 'BACKUP_RETENTION_COUNT', 7))))
    try:
        from scripts.backup_data import run_backup, cleanup_old_backups
        zip_path, count = run_backup()
        logger.info("定时备份完成: %s (%d 个文件)", zip_path, count)
        cleaned = cleanup_old_backups(retain=retain)
        if cleaned > 0:
            logger.info("已清理 %d 个旧备份（保留最近 %d 份）", cleaned, retain)
    except Exception as e:
        logger.warning("定时备份失败: %s", e)


def run_background_scheduler():
    """后台：每小时告警检查，每日定点发报表邮件，每日定点备份。"""
    import time
    last_report_date = None
    last_backup_date = None
    backup_hour = int(os.getenv('BACKUP_HOUR', str(getattr(Config, 'BACKUP_HOUR', 2))))
    while True:
        try:
            now = datetime.now()
            _run_alert_check()
            if Config.REPORT_EMAIL_TO and now.hour == getattr(Config, 'REPORT_HOUR', 8):
                if last_report_date is None or last_report_date != now.date():
                    _send_report_email()
                    last_report_date = now.date()
            # 商业级：每日定点备份（可配置 BACKUP_SCHEDULED=false 禁用）
            if getattr(Config, 'BACKUP_SCHEDULED', True) and now.hour == backup_hour and (last_backup_date is None or last_backup_date != now.date()):
                _run_scheduled_backup()
                last_backup_date = now.date()
        except Exception as e:
            logger.warning("scheduler: %s", e)
        time.sleep(3600)


def start_download_service():
    """启动 8888 端口直链下载服务；若端口已被占用则跳过。"""
    import subprocess as _subprocess
    download_port = 8888
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(0.5)
        s.connect(('127.0.0.1', download_port))
        s.close()
        return
    except Exception:
        pass
    if not os.path.isdir(Config.APK_DIR):
        return
    try:
        _subprocess.Popen(
            [sys.executable, '-m', 'http.server', str(download_port), '--bind', '0.0.0.0'],
            cwd=Config.APK_DIR,
            stdout=_subprocess.DEVNULL,
            stderr=_subprocess.DEVNULL,
            start_new_session=True,
        )
        logger.info("下载直链服务已启动: http://0.0.0.0:%s（目录: %s）", download_port, Config.APK_DIR)
    except Exception as e:
        logger.warning("启动下载直链服务失败: %s", e)


def write_base_url_file():
    """写入 .apk-site-base-url 供 Jenkins 脚本读取。外网部署时优先使用 PUBLIC_URL。"""
    base_url = Config.get_public_base_url() or get_canonical_base_url()
    path = os.path.join(Config.APK_DIR, '.apk-site-base-url')
    try:
        if os.path.isdir(Config.APK_DIR):
            with open(path, 'w', encoding='utf-8') as f:
                f.write(base_url)
    except Exception as e:
        logger.warning("写入 .apk-site-base-url 失败: %s", e)
    return base_url


def write_jenkins_clone_env():
    """写入 jenkins-clone/.apk-site-env，复制到 apk-site 后脚本可直接用。"""
    if not os.path.isdir(JENKINS_CLONE_DIR):
        return
    env_path = os.path.join(JENKINS_CLONE_DIR, '.apk-site-env')
    job_builds = os.path.join(JENKINS_CLONE_DIR, 'jobs', 'Android', 'builds')
    try:
        with open(env_path, 'w', encoding='utf-8') as f:
            f.write('# apk-site 启动时写入，供 jenkins-clone 内脚本 source 使用\n')
            f.write('export APK_DIR="%s"\n' % Config.APK_DIR.replace('"', '\\"'))
            f.write('export JENKINS_CLONE="%s"\n' % JENKINS_CLONE_DIR.replace('"', '\\"'))
            f.write('export JENKINS_JOB_DIR="%s"\n' % job_builds.replace('"', '\\"'))
        logger.info("已写入 %s", env_path)
    except Exception as e:
        logger.warning("写入 .apk-site-env 失败: %s", e)


def apply_jenkins_clone_overlay():
    """若存在 jenkins-clone，用 overlay 覆盖脚本与 Job 配置，使复制即用。"""
    if not os.path.isdir(JENKINS_CLONE_DIR):
        return
    overlay_root = _resolve_overlay_root()
    if not os.path.isdir(overlay_root):
        return
    try:
        # 供 shell 等使用的转义；XML 内用原始路径即可（路径一般无 <>&"）
        apk_dir_raw = Config.APK_DIR
        apk_dir_esc = apk_dir_raw.replace('\\', '\\\\').replace('"', '\\"')
        _copy_overlay_dir(overlay_root, JENKINS_CLONE_DIR, '', apk_dir_esc, apk_dir_raw)
    except Exception as e:
        logger.warning("应用 jenkins-clone overlay 失败: %s", e)


def _copy_overlay_dir(src_dir, dst_dir, rel_label, apk_dir_esc, apk_dir_raw=None):
    if apk_dir_raw is None:
        apk_dir_raw = apk_dir_esc
    os.makedirs(dst_dir, exist_ok=True)
    for name in os.listdir(src_dir):
        if name in ('.DS_Store', '__pycache__') or name.startswith('._'):
            continue
        s = os.path.join(src_dir, name)
        d = os.path.join(dst_dir, name)
        if os.path.isfile(s):
            if name.endswith(('.pyc', '.pyo')):
                continue
            content = open(s, 'r', encoding='utf-8', errors='replace').read()
            # XML 用原始路径；shell 等用转义（此处统一用 raw，XML 中无引号）
            content = content.replace('{{APK_DIR}}', apk_dir_raw)
            with open(d, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info("已覆盖 jenkins-clone/%s", (rel_label + '/' + name).lstrip('/'))
        elif os.path.isdir(s):
            _copy_overlay_dir(s, d, (rel_label + '/' + name).lstrip('/'), apk_dir_esc, apk_dir_raw)
