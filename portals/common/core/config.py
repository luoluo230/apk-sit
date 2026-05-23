# -*- coding: utf-8 -*-
"""APK 下载中心 - 配置与环境。优先从 config/settings.json 读取，环境变量可覆盖。"""

import os
import json
import secrets

# 项目根与 Jenkins 集成目录（支持代码收敛到 portals/common/core）
_APP_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT_FROM_CORE = os.path.abspath(os.path.join(_APP_DIR, '..', '..', '..'))
APK_SITE_ROOT = _ROOT_FROM_CORE if os.path.isdir(os.path.join(_ROOT_FROM_CORE, 'portals')) else _APP_DIR
JENKINS_CLONE_DIR = (
    os.path.join(APK_SITE_ROOT, 'jenkins-clone')
    if os.path.isdir(os.path.join(APK_SITE_ROOT, 'jenkins-clone'))
    else os.path.join(_APP_DIR, 'jenkins-clone')
)
DATA_DIR = os.path.join(APK_SITE_ROOT, 'data')
CONFIG_DIR = os.path.join(_APP_DIR, 'config')
SETTINGS_FILE = os.path.join(CONFIG_DIR, 'settings.json')
SETTINGS_EXAMPLE = os.path.join(CONFIG_DIR, 'settings.example.json')
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(CONFIG_DIR, exist_ok=True)


def _load_settings():
    """从 config/settings.json 或 settings.example.json 加载配置，过滤 _ 开头的键。"""
    if not os.path.isfile(SETTINGS_FILE) and os.path.isfile(SETTINGS_EXAMPLE):
        try:
            import shutil
            shutil.copy(SETTINGS_EXAMPLE, SETTINGS_FILE)
        except Exception:
            pass
    out = {}
    for path in [SETTINGS_FILE, SETTINGS_EXAMPLE]:
        if os.path.isfile(path):
            try:
                with open(path, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                if isinstance(data, dict):
                    for k, v in data.items():
                        if not k.startswith('_') and isinstance(v, dict):
                            out[k] = {kk: vv for kk, vv in v.items() if not kk.startswith('_')}
            except Exception:
                pass
            break
    return out


_SETTINGS = _load_settings()


def _get(path, default=None, env_key=None):
    """从 settings 读取：path 如 'app.port'。env_key 存在时用 os.getenv 覆盖。"""
    parts = path.split('.')
    val = _SETTINGS
    for p in parts:
        val = (val or {}).get(p)
        if val is None:
            break
    if env_key and os.getenv(env_key) not in (None, ''):
        return os.getenv(env_key)
    return val


def _load_dotenv_file(env_path):
    if not env_path or not os.path.isfile(env_path):
        return
    try:
        with open(env_path, 'r', encoding='utf-8', errors='ignore') as f:
            for line in f:
                line = line.replace('\r', '').strip()
                if not line or line.startswith('#'):
                    continue
                idx = line.find('=')
                if idx <= 0:
                    continue
                key = line[:idx].strip()
                value = line[idx + 1:].strip().strip('"').strip("'")
                if key and key not in os.environ:
                    os.environ[key] = value
    except Exception:
        pass


def load_dotenv():
    """从应用目录与当前工作目录加载 .env"""
    env_app = os.path.join(APK_SITE_ROOT, '.env')
    env_cwd = os.path.join(os.getcwd(), '.env')
    if not os.path.isfile(env_app) and not os.path.isfile(env_cwd):
        example = os.path.join(APK_SITE_ROOT, '.env.example')
        if os.path.isfile(example):
            try:
                import shutil
                shutil.copy(example, env_app)
            except Exception:
                pass
    for path in [env_app, env_cwd]:
        _load_dotenv_file(path)


def _jenkins_credentials_path():
    return os.path.join(APK_SITE_ROOT, 'jenkins_credentials.json')


def get_jenkins_credentials():
    """先加载 .env，再读 jenkins_credentials.json，最后 os.environ。"""
    load_dotenv()
    user, token = '', ''
    cred_path = _jenkins_credentials_path()
    if os.path.isfile(cred_path):
        try:
            with open(cred_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            user = (data.get('JENKINS_USER') or data.get('user') or '').strip()
            token = (data.get('JENKINS_TOKEN') or data.get('JENKINS_PASSWORD') or data.get('token') or '').strip()
        except Exception:
            pass
    if not user:
        user = (os.getenv('JENKINS_USER') or '').strip()
    if not token:
        token = (os.getenv('JENKINS_TOKEN') or os.getenv('JENKINS_PASSWORD') or '').strip()
    return (user, token)


def _resolve_path(val, base=APK_SITE_ROOT):
    """相对路径转为绝对路径。"""
    if not val:
        return ''
    val = str(val).strip()
    if not os.path.isabs(val):
        val = os.path.normpath(os.path.join(base, val))
    return val


# Load .env before evaluating Config class attributes, so env overrides
# are effective during module import.
load_dotenv()


class Config:
    """配置类：优先 config/settings.json，环境变量可覆盖。"""
    _apk_dir = _get('apk.dir') or os.getenv('APK_DIR', 'data/apk')
    APK_DIR = _resolve_path(os.getenv('APK_DIR', _apk_dir))
    PORT = int(os.getenv('APK_PORT') or _get('app.port') or '5003')
    HOST = str(os.getenv('APK_HOST') or _get('app.host') or '0.0.0.0')
    PLAYER_PORT = int(os.getenv('PLAYER_PORT') or _get('portal.player_port') or '5004')
    FORUM_PORT = int(os.getenv('FORUM_PORT') or _get('portal.forum_port') or '5005')
    ADMIN_PORT = int(os.getenv('ADMIN_PORT') or _get('portal.admin_port') or PORT)
    PORTAL_MODE = (os.getenv('APP_PORTAL_MODE') or _get('portal.mode') or 'all').strip().lower()
    PLAYER_DOMAIN = (os.getenv('PLAYER_DOMAIN') or _get('portal.player_domain') or '').strip()
    FORUM_DOMAIN = (os.getenv('FORUM_DOMAIN') or _get('portal.forum_domain') or '').strip()
    ADMIN_DOMAIN = (os.getenv('ADMIN_DOMAIN') or _get('portal.admin_domain') or '').strip()
    PLAYER_PUBLIC_URL = (os.getenv('PLAYER_PUBLIC_URL') or _get('portal.player_public_url') or '').strip().rstrip('/')
    FORUM_PUBLIC_URL = (os.getenv('FORUM_PUBLIC_URL') or _get('portal.forum_public_url') or '').strip().rstrip('/')
    ADMIN_PUBLIC_URL = (os.getenv('ADMIN_PUBLIC_URL') or _get('portal.admin_public_url') or '').strip().rstrip('/')
    _log_dir = _get('app.log_dir') or 'logs'
    LOG_DIR = _resolve_path(os.getenv('APK_LOG_DIR', _log_dir))
    DEBUG = (os.getenv('APK_DEBUG') or str(_get('app.debug', False))).lower() in ('true', '1', 'yes')

    _jenkins_url = _get('jenkins.url') or ''
    JENKINS_URL = (os.getenv('JENKINS_URL') or _jenkins_url or ('http://localhost:' + (os.getenv('JENKINS_PORT') or _get('jenkins.port') or '8080'))).strip()
    JENKINS_USER = (os.getenv('JENKINS_USER') or '').strip()
    JENKINS_TOKEN = (os.getenv('JENKINS_TOKEN') or os.getenv('JENKINS_PASSWORD') or '').strip()
    _jenkins_image = _get('jenkins.image') or 'jenkins/jenkins:lts-jdk17'
    JENKINS_DOCKER_IMAGE = (os.getenv('JENKINS_DOCKER_IMAGE') or _jenkins_image).strip() or 'jenkins/jenkins:lts-jdk17'
    JENKINS_CONTAINER_NAME = (
        os.getenv('JENKINS_CONTAINER_NAME') or _get('jenkins.container_name') or 'apk-site-jenkins'
    ).strip() or 'apk-site-jenkins'
    _builds = _get('jenkins.builds_dir') or 'data/jenkins_instances/default/jobs/Android/builds'
    JENKINS_BUILDS_DIR = _resolve_path(os.getenv('JENKINS_BUILDS_DIR', _builds))
    JENKINS_WAR_PATH = (os.getenv('JENKINS_WAR_PATH') or _get('jenkins.war_path') or '').strip()
    _inst = _get('jenkins.instances_dir') or 'data/jenkins_instances'
    JENKINS_INSTANCES_DIR = _resolve_path(os.getenv('JENKINS_INSTANCES_DIR', _inst))
    JENKINS_JOB_NAME = (os.getenv('JENKINS_JOB_NAME') or _get('jenkins.job_name') or 'Android').strip()
    JENKINS_DEFAULT_USER = (os.getenv('JENKINS_DEFAULT_USER') or _get('jenkins.default_user') or 'admin').strip() or 'admin'
    JENKINS_DEFAULT_PASSWORD = (os.getenv('JENKINS_DEFAULT_PASSWORD') or _get('jenkins.default_password') or 'admin123').strip() or 'admin123'

    _force = _get('security.force_login')
    FORCE_LOGIN = (os.getenv('FORCE_LOGIN') or str(_force if _force is not None else True)).lower() in ('true', '1', 'yes')
    _inner = _get('security.inner_net') or '192.168.,10.,127.,26.26.'
    INNER_NET = [x.strip() for x in (os.getenv('INNER_NET', _inner).split(',')) if x.strip()]
    IP_WHITELIST_RAW = os.getenv('IP_WHITELIST') or _get('security.ip_whitelist') or ''
    IP_WHITELIST = [ip.strip() for ip in IP_WHITELIST_RAW.split(',') if ip.strip()] if IP_WHITELIST_RAW else None
    _login_limit = _get('security.login_attempts_limit')
    LOGIN_ATTEMPTS_LIMIT = int(os.getenv('LOGIN_ATTEMPTS_LIMIT') or _login_limit or '5')
    _lockout = _get('security.login_lockout_minutes')
    LOGIN_LOCKOUT_MINUTES = int(os.getenv('LOGIN_LOCKOUT_MINUTES') or _lockout or '15')
    SECRET_KEY = None

    SMTP_HOST = (os.getenv('SMTP_HOST') or _get('smtp.host') or '').strip()
    SMTP_PORT = int(os.getenv('SMTP_PORT') or _get('smtp.port') or '0')
    SMTP_USER = (os.getenv('SMTP_USER') or _get('smtp.user') or '').strip()
    SMTP_PASSWORD = (os.getenv('SMTP_PASSWORD') or _get('smtp.password') or '').strip()
    REPORT_EMAIL_TO = (os.getenv('REPORT_EMAIL_TO') or _get('smtp.report_email_to') or '').strip()
    REPORT_HOUR = int(os.getenv('REPORT_HOUR') or _get('smtp.report_hour') or '8')

    BACKUP_SCHEDULED = (os.getenv('BACKUP_SCHEDULED') or 'true').lower() in ('true', '1', 'yes')
    BACKUP_HOUR = int(os.getenv('BACKUP_HOUR') or _get('backup.hour') or '2')
    BACKUP_RETENTION_COUNT = int(os.getenv('BACKUP_RETENTION_COUNT') or _get('backup.retention_count') or '7')
    ALERT_FEISHU_WEBHOOK = (os.getenv('ALERT_FEISHU_WEBHOOK') or _get('feishu.webhook') or '').strip()
    DISK_ALERT_GB = float(os.getenv('DISK_ALERT_GB') or _get('feishu.disk_alert_gb') or '5')

    USE_SQLITE = str(os.getenv('USE_SQLITE') or _get('app.use_sqlite') or 'true').lower() in ('true', '1', 'yes')
    SQLITE_MIRROR_JSON = str(os.getenv('SQLITE_MIRROR_JSON') or _get('app.sqlite_mirror_json') or 'false').lower() in ('true', '1', 'yes')
    SQLITE_IMPORT_JSON_ON_MISS = str(
        os.getenv('SQLITE_IMPORT_JSON_ON_MISS') or _get('app.sqlite_import_json_on_miss') or 'false'
    ).lower() in ('true', '1', 'yes')
    PUBLIC_URL = (os.getenv('PUBLIC_URL') or _get('external.public_url') or '').strip()
    EXTERNAL_DOMAIN = (os.getenv('EXTERNAL_DOMAIN') or _get('external.external_domain') or '').strip()

    WORKSPACE_BASE_DIR = _resolve_path(_get('workspace.base_dir') or 'data/workspaces')
    DOCS_ATTACHMENTS_DIR = _resolve_path(_get('docs.attachments_dir') or 'data/doc_attachments')
    DOCS_MAX_ATTACHMENT_MB = float(_get('docs.max_attachment_mb') or 20)

    @classmethod
    def get_public_base_url(cls):
        """对外展示的 base URL。优先 PUBLIC_URL，否则由 EXTERNAL_DOMAIN 推断。运行时读取 env，兼容 load_dotenv 在 Config 之后执行。"""
        pub = (os.getenv('PUBLIC_URL') or '').strip()
        if pub:
            return pub.rstrip('/')
        ext = (os.getenv('EXTERNAL_DOMAIN') or '').strip()
        if ext:
            d = ext.replace('http://', '').replace('https://', '').strip().rstrip('/')
            return ('https://' if 'localhost' not in d else 'http://') + d
        return ''

    @classmethod
    def get_secret_key(cls):
        if cls.SECRET_KEY:
            return cls.SECRET_KEY
        env_key = os.getenv('APK_SECRET')
        if env_key:
            cls.SECRET_KEY = env_key
            return env_key
        secret_file = os.path.join(DATA_DIR, 'secret.key')
        if os.path.exists(secret_file):
            with open(secret_file, 'r') as f:
                cls.SECRET_KEY = f.read().strip()
        else:
            cls.SECRET_KEY = secrets.token_hex(32)
            with open(secret_file, 'w') as f:
                f.write(cls.SECRET_KEY)
        return cls.SECRET_KEY
