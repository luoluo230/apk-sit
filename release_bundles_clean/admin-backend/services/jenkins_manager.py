# -*- coding: utf-8 -*-
"""Jenkins 多实例管理：端口检测、启动/停止、环境检查与一键部署、实例默认构建参数"""

import os
import sys
import socket
import subprocess
import platform
import uuid
import logging
from datetime import datetime

from config import Config, JENKINS_CLONE_DIR
from models.data import load_jenkins_instances, save_jenkins_instances, channels_db

logger = logging.getLogger(__name__)


def _xml_esc(s):
    if s is None:
        return ''
    s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    return s


def _build_param_defs_xml(build_defaults, output_base):
    """根据实例的 build_defaults 生成 Jenkins 任务 parameterDefinitions 的 XML 片段。"""
    d = build_defaults or {}
    app_name = (d.get('app_name') or '').strip() or 'GameKu'
    version_name = (d.get('version_name') or '').strip() or '1.0.0'
    version_code = (d.get('version_code') or '').strip() or '1'
    out_dir = (d.get('output_base_dir') or '').strip() or output_base
    unity_versions = d.get('unity_versions') or []
    if not isinstance(unity_versions, list):
        unity_versions = []
    unity_choices = []
    for u in unity_versions:
        if isinstance(u, dict) and u.get('version'):
            unity_choices.append(str(u.get('version', '')).strip())
        elif isinstance(u, str) and u.strip():
            unity_choices.append(u.strip())
    if not unity_choices:
        unity_choices = ['6000.3.8f1']
    default_unity = unity_choices[0] if unity_choices else '6000.3.8f1'
    git_branches = d.get('git_branches') or []
    if not isinstance(git_branches, list):
        git_branches = [b.strip() for b in str(git_branches).split('\n') if b.strip()]
    if not git_branches:
        git_branches = ['main']
    default_branch = (d.get('default_git_branch') or '').strip()
    if default_branch and default_branch in git_branches:
        git_branches = [default_branch] + [b for b in git_branches if b != default_branch]
    lines = [
        '<hudson.model.ChoiceParameterDefinition>',
        '  <name>UNITY_VERSION</name>',
        '  <description>Unity 版本（对应安装路径见 JENKINS_HOME/unity_paths.json）</description>',
        '  <choices class="java.util.Arrays$ArrayList"><a class="string-array">',
    ]
    for c in unity_choices:
        lines.append('    <string>%s</string>' % _xml_esc(c))
    lines.extend([
        '  </a></choices>',
        '</hudson.model.ChoiceParameterDefinition>',
        '<hudson.model.StringParameterDefinition>',
        '  <name>VERSION_NAME</name><description>版本号</description><defaultValue>%s</defaultValue><trim>true</trim>' % _xml_esc(version_name),
        '</hudson.model.StringParameterDefinition>',
        '<hudson.model.StringParameterDefinition>',
        '  <name>VERSION_CODE</name><description>版本代码</description><defaultValue>%s</defaultValue><trim>true</trim>' % _xml_esc(version_code),
        '</hudson.model.StringParameterDefinition>',
        '<hudson.model.StringParameterDefinition>',
        '  <name>APP_NAME</name><description>应用名称</description><defaultValue>%s</defaultValue><trim>true</trim>' % _xml_esc(app_name),
        '</hudson.model.StringParameterDefinition>',
        '<hudson.model.StringParameterDefinition>',
        '  <name>OUTPUT_BASE_DIR</name><description>输出基础目录</description><defaultValue>%s</defaultValue><trim>true</trim>' % _xml_esc(out_dir),
        '</hudson.model.StringParameterDefinition>',
        '<hudson.model.ChoiceParameterDefinition>',
        '  <name>GIT_BRANCH</name><description>Git 分支</description>',
        '  <choices class="java.util.Arrays$ArrayList"><a class="string-array">',
    ])
    for b in git_branches:
        lines.append('    <string>%s</string>' % _xml_esc(b))
    lines.extend([
        '  </a></choices>',
        '</hudson.model.ChoiceParameterDefinition>',
    ])
    channel_ids = ['dev', 'test', 'production']
    if isinstance(channels_db, list) and channels_db:
        channel_ids = [(c.get('id') or '').strip() for c in channels_db if (c.get('id') or '').strip()]
    if channel_ids:
        lines.extend([
            '<hudson.model.ChoiceParameterDefinition>',
            '  <name>CHANNEL</name>',
            '  <description>渠道（dev/test/production 等，用于多渠道构建与输出子目录）</description>',
            '  <choices class="java.util.Arrays$ArrayList"><a class="string-array">',
            '    <string></string>',
        ])
        for cid in channel_ids:
            lines.append('    <string>%s</string>' % _xml_esc(cid))
        lines.extend([
            '  </a></choices>',
            '</hudson.model.ChoiceParameterDefinition>',
        ])
    return '\n'.join(lines)

INSTANCES_DIR = Config.JENKINS_INSTANCES_DIR
os.makedirs(INSTANCES_DIR, exist_ok=True)


def validate_git_config(git_url, git_workspace, git_ssh_key_path):
    """校验 Git 相关配置（工作目录、仓库 URL、SSH 密钥路径）。返回 (ok: bool, errors: list[str])。"""
    errors = []
    git_url = (git_url or '').strip()
    git_workspace = (git_workspace or '').strip()
    git_ssh_key_path = (git_ssh_key_path or '').strip()

    has_url = bool(git_url)
    has_workspace = bool(git_workspace)
    has_key = bool(git_ssh_key_path)

    if has_url and not has_workspace:
        errors.append('已填写 Git 仓库 URL 时，请同时填写 Git 工作目录（clone/pull 目标路径）')
    if has_workspace and not has_url:
        errors.append('已填写 Git 工作目录时，请同时填写 Git 仓库 URL')

    if has_url:
        if not (git_url.startswith('git@') or git_url.startswith('https://') or git_url.startswith('http://')):
            errors.append('Git 仓库 URL 格式有误，应为 git@... 或 https://... 或 http://...')
        if '..' in git_url or git_url.count(' ') > 0:
            errors.append('Git 仓库 URL 不宜包含 .. 或空格')

    if has_workspace:
        expanded = os.path.expanduser(git_workspace)
        if not os.path.isabs(expanded):
            errors.append('Git 工作目录请使用绝对路径')
        elif os.path.exists(expanded):
            if not os.path.isdir(expanded):
                errors.append('Git 工作目录路径已存在且不是目录，请指定一个目录路径')
            elif has_url and os.path.exists(os.path.join(expanded, '.git')):
                if not os.access(expanded, os.W_OK):
                    errors.append('Git 工作目录无写权限，无法执行 git pull')
        else:
            parent = os.path.dirname(expanded)
            if not parent or parent == expanded:
                errors.append('Git 工作目录的父路径无效')
            elif not os.path.exists(parent):
                errors.append('Git 工作目录的父目录不存在，请先创建或改用已存在目录')
            elif not os.path.isdir(parent):
                errors.append('Git 工作目录的父路径不是目录')
            elif not os.access(parent, os.W_OK):
                errors.append('Git 工作目录的父目录无写权限，无法执行 git clone')

    if has_key:
        expanded_key = os.path.expanduser(git_ssh_key_path)
        if not os.path.isfile(expanded_key):
            errors.append('Git SSH 密钥路径指向的文件不存在或不是文件：%s' % expanded_key)
        elif not os.access(expanded_key, os.R_OK):
            errors.append('Git SSH 密钥文件无读权限')

    return (len(errors) == 0, errors)


def check_port(port):
    """检测端口是否可用（未被占用）。返回 (ok: bool, message: str)。"""
    try:
        p = int(port)
        if p <= 0 or p > 65535:
            return (False, "端口需在 1-65535 之间")
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(1)
        try:
            sock.bind(('127.0.0.1', p))
            return (True, "端口 %s 可用" % p)
        except OSError as e:
            return (False, "端口 %s 已被占用或不可用: %s" % (p, e))
        finally:
            sock.close()
    except ValueError:
        return (False, "请输入有效端口号")


def _get_pid_by_port(port):
    """根据端口查找进程 PID。Mac/Linux 用 lsof，Windows 用 netstat。"""
    try:
        port = int(port)
        if sys.platform == 'darwin' or sys.platform.startswith('linux'):
            out = subprocess.check_output(
                ['lsof', '-ti', ':%d' % port],
                stderr=subprocess.DEVNULL,
                timeout=5
            )
            if out.strip():
                return int(out.strip().decode().split()[0])
        elif sys.platform == 'win32':
            out = subprocess.check_output(
                ['netstat', '-ano'],
                stderr=subprocess.DEVNULL,
                timeout=5,
                creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, 'CREATE_NO_WINDOW') else 0
            )
            for line in out.decode(errors='ignore').splitlines():
                parts = line.split()
                if len(parts) >= 5 and ':%d' % port in line and 'LISTENING' in line:
                    return int(parts[-1])
        return None
    except Exception as e:
        logger.warning("get_pid_by_port %s: %s", port, e)
        return None


def _is_process_alive(pid):
    try:
        if pid is None:
            return False
        if sys.platform == 'win32':
            subprocess.check_call(['tasklist', '/FI', 'PID eq %d' % pid], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, timeout=2)
            return True
        os.kill(pid, 0)
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def get_jenkins_war_path():
    """返回可用的 jenkins.war 路径。优先 JENKINS_WAR_PATH，其次 jenkins-clone/jenkins.war，再 data/jenkins_instances/jenkins.war。"""
    if Config.JENKINS_WAR_PATH and os.path.isfile(Config.JENKINS_WAR_PATH):
        return Config.JENKINS_WAR_PATH
    war_in_clone = os.path.join(JENKINS_CLONE_DIR, 'jenkins.war')
    if os.path.isfile(war_in_clone):
        return war_in_clone
    cached = os.path.join(INSTANCES_DIR, 'jenkins.war')
    if os.path.isfile(cached):
        return cached
    return None


def env_check():
    """检查 Jenkins 运行环境。返回 {java: {ok, version, path}, git: {ok, version}, war: {ok, path}}。"""
    result = {'java': {'ok': False, 'version': '', 'path': ''}, 'git': {'ok': False, 'version': ''}, 'war': {'ok': False, 'path': ''}}
    # Java
    try:
        out = subprocess.check_output(['java', '-version'], stderr=subprocess.STDOUT, timeout=5)
        text = (out or b'').decode(errors='ignore')
        result['java']['ok'] = True
        for line in text.splitlines():
            if 'version' in line:
                result['java']['version'] = line.strip()
                break
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired) as e:
        result['java']['version'] = str(e)
    # Git
    try:
        out = subprocess.check_output(['git', '--version'], stderr=subprocess.DEVNULL, timeout=3)
        result['git']['ok'] = True
        result['git']['version'] = out.decode().strip()
    except Exception:
        pass
    # War
    war_path = get_jenkins_war_path()
    result['war']['ok'] = bool(war_path and os.path.isfile(war_path))
    result['war']['path'] = war_path or ''
    return result


def deploy_env_script(platform_name):
    """返回当前平台的一键部署脚本内容（安装 Java / 下载 war）。"""
    if platform_name in ('darwin', 'mac', 'macos'):
        return '''# Mac 部署 Jenkins 环境
# 1. 安装 Java（若未安装）
brew install openjdk@17  # 或 brew install openjdk@11
# 2. 下载 Jenkins war（可选，本系统也会自动使用已配置的 JENKINS_WAR_PATH）
# curl -L -o jenkins.war https://get.jenkins.io/war-stable/latest/jenkins.war
'''
    if platform_name in ('win32', 'windows'):
        return '''# Windows 部署 Jenkins 环境
# 1. 安装 Java：从 https://adoptium.net/ 下载并安装 JDK 17
# 2. 或将 Jenkins war 路径配置到环境变量 JENKINS_WAR_PATH
# 下载 war: https://get.jenkins.io/war-stable/latest/jenkins.war
'''
    return "# 当前平台: %s\n# 请手动安装 Java 并配置 JENKINS_WAR_PATH\n" % platform_name


def run_deploy_env(log_path):
    """执行环境部署（Mac: 尝试 brew install openjdk；Windows: 提示）。将输出写入 log_path。"""
    import threading
    def _run():
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("开始时间: %s\n" % datetime.now().isoformat())
            f.write("平台: %s\n" % platform.system())
            try:
                if sys.platform == 'darwin':
                    f.write("尝试安装 OpenJDK (brew install openjdk@17)...\n")
                    f.flush()
                    p = subprocess.Popen(
                        ['brew', 'install', 'openjdk@17'],
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                        text=True, cwd=os.path.expanduser('~')
                    )
                    for line in p.stdout:
                        f.write(line)
                        f.flush()
                    p.wait()
                    f.write("\n退出码: %s\n" % p.returncode)
                else:
                    f.write("Windows 请手动安装 JDK 并设置 JENKINS_WAR_PATH。\n")
            except Exception as e:
                f.write("错误: %s\n" % e)
            f.write("结束时间: %s\n" % datetime.now().isoformat())
    t = threading.Thread(target=_run, daemon=True)
    t.start()
    return log_path


def _write_jenkins_init_admin_script(jenkins_home, user, password):
    """在 JENKINS_HOME/init.groovy.d 写入创建固定管理员的 Groovy 脚本，首次启动时自动执行。"""
    init_d = os.path.join(jenkins_home, 'init.groovy.d')
    os.makedirs(init_d, exist_ok=True)
    # Groovy 字符串转义：避免用户名/密码中的引号或反斜杠破坏脚本
    u = (user or 'admin').replace('\\', '\\\\').replace('"', '\\"')
    p = (password or 'admin123').replace('\\', '\\\\').replace('"', '\\"')
    script = '''// apk-site 注入：管理内实例固定管理员，始终覆盖以便 API 可用
import jenkins.model.*
import hudson.security.*

def j = Jenkins.getInstance()
def realm = new HudsonPrivateSecurityRealm(false)
realm.createAccount("%s", "%s")
j.setSecurityRealm(realm)
j.setAuthorizationStrategy(new hudson.security.FullControlOnceLoggedInAuthorizationStrategy())
j.save()
''' % (u, p)
    path = os.path.join(init_d, '00-create-admin.groovy')
    with open(path, 'w', encoding='utf-8') as f:
        f.write(script)
    logger.info("已写入 %s", path)


def _copy_android_job_to_jenkins_home(jenkins_home, port=None, task_name=None, build_defaults=None):
    """把 overlay 里的 Android 任务复制到新实例的 JENKINS_HOME；OUTPUT_BASE_DIR 按任务名/端口隔离。
    若提供 build_defaults，则生成带下拉与默认值的参数（Unity 版本、分支等），并写入 unity_paths.json。"""
    try:
        job_dir = os.path.join(jenkins_home, 'jobs', 'Android')
        config_path = os.path.join(job_dir, 'config.xml')
        overlay_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'jenkins-clone-overlay')
        config_src = os.path.join(overlay_root, 'jobs', 'Android', 'config.xml')
        if not os.path.isfile(config_src):
            return
        subdir = (task_name or '').strip() if (task_name and str(task_name).strip()) else ('jenkins_' + str(port or ''))
        output_base = os.path.join(Config.APK_DIR, subdir) if subdir else Config.APK_DIR
        builds_dir = os.path.join(job_dir, 'builds')
        os.makedirs(builds_dir, exist_ok=True)

        if build_defaults:
            content = _generate_job_config_xml(output_base, build_defaults)
        else:
            with open(config_src, 'r', encoding='utf-8') as f:
                content = f.read()
            content = content.replace('{{APK_DIR}}', output_base)

        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)
        next_num = os.path.join(job_dir, 'nextBuildNumber')
        if not os.path.isfile(next_num):
            with open(next_num, 'w') as f:
                f.write('1')

        # Unity 版本 -> 安装路径映射，供构建脚本读取
        unity_versions = (build_defaults or {}).get('unity_versions') or []
        if False and isinstance(unity_versions, list) and unity_versions:
            paths = {}
            for u in unity_versions:
                if isinstance(u, dict) and u.get('version'):
                    paths[str(u.get('version', '')).strip()] = (u.get('path') or '').strip()
            if paths:
                paths_file = os.path.join(jenkins_home, 'unity_paths.json')
                try:
                    with open(paths_file, 'w', encoding='utf-8') as f:
                        f.write('')
                    logger.info("已写入 %s", paths_file)
                except Exception as e:
                    logger.warning("写入 unity_paths.json 失败: %s", e)

        logger.info("已写入 Android 任务到 %s（输出目录: %s）", job_dir, output_base)
    except Exception as e:
        logger.warning("复制 Android 任务失败: %s", e)


def _generate_job_config_xml(output_base, build_defaults):
    """根据 output_base 与 build_defaults 生成完整 Android job config.xml 内容。"""
    overlay_root = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'jenkins-clone-overlay')
    config_src = os.path.join(overlay_root, 'jobs', 'Android', 'config.xml')
    with open(config_src, 'r', encoding='utf-8') as f:
        content = f.read()
    param_xml = _build_param_defs_xml(build_defaults, output_base)
    import re
    content = re.sub(
        r'<parameterDefinitions>.*?</parameterDefinitions>',
        '<parameterDefinitions>\n%s\n      </parameterDefinitions>' % param_xml,
        content,
        flags=re.DOTALL
    )
    content = content.replace('{{APK_DIR}}', output_base)
    return content


def get_instance_output_base(inst):
    """返回该实例的默认构建输出根目录（与 job 内 OUTPUT_BASE_DIR 一致）。"""
    if not inst:
        return Config.APK_DIR
    bd = inst.get('build_defaults') or {}
    out_dir = (bd.get('output_base_dir') or '').strip()
    if out_dir:
        return out_dir
    task_name = (inst.get('task_name') or '').strip()
    port = inst.get('port')
    subdir = task_name if task_name else ('jenkins_' + str(port) if port is not None else '')
    return os.path.join(Config.APK_DIR, subdir) if subdir else Config.APK_DIR


def _write_instance_env_and_scripts(jenkins_home, port, task_name, output_base, feishu_webhook='', build_defaults=None):
    """为管理内实例写入 .apk-site-env、.apk-site-feishu，并复制通知脚本；build_defaults 含 git_url、git_ssh_key_path 等时一并写入。"""
    from services import startup
    base_url = startup.get_canonical_base_url()  # 与启动横幅一致：局域网 IP:PORT
    env_path = os.path.join(jenkins_home, '.apk-site-env')
    job_builds = os.path.join(jenkins_home, 'jobs', 'Android', 'builds')
    apk_scan_dir = Config.APK_DIR.replace('\\', '\\\\').replace('"', '\\"')
    def esc(s):
        return (s or '').replace('\\', '\\\\').replace('"', '\\"')
    lines = [
        '# 本实例环境，构建步骤会 source 此文件',
        'export JENKINS_CLONE="%s"' % esc(jenkins_home),
        'export APK_DIR="%s"' % esc(output_base),
        'export APK_SCAN_DIR="%s"' % apk_scan_dir,
        'export JENKINS_JOB_DIR="%s"' % esc(job_builds),
        'export APKSITE_BASE_URL="%s"' % esc(base_url),
    ]
    bd = build_defaults or {}
    if (bd.get('git_url') or '').strip():
        lines.append('export GIT_URL="%s"' % esc((bd.get('git_url') or '').strip()))
    if (bd.get('git_ssh_key_path') or '').strip():
        lines.append('export GIT_SSH_KEY_PATH="%s"' % esc((bd.get('git_ssh_key_path') or '').strip()))
    if (bd.get('git_workspace') or '').strip():
        lines.append('export GIT_WORKSPACE="%s"' % esc((bd.get('git_workspace') or '').strip()))
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    logger.info("已写入 %s（APKSITE_BASE_URL=%s）", env_path, base_url)
    if (feishu_webhook or '').strip():
        feishu_path = os.path.join(jenkins_home, '.apk-site-feishu')
        webhook = (feishu_webhook or '').strip().replace('"', '\\"')
        with open(feishu_path, 'w', encoding='utf-8') as f:
            f.write('export FEISHU_WEBHOOK="%s"\n' % webhook)
        logger.info("已写入 %s", feishu_path)
    overlay_scripts = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'jenkins-clone-overlay', 'scripts')
    scripts_dst = os.path.join(jenkins_home, 'scripts')
    os.makedirs(scripts_dst, exist_ok=True)
    for name in ('jenkins_send_notify.sh', 'feishu_send.py'):
        src = os.path.join(overlay_scripts, name)
        if os.path.isfile(src):
            import shutil
            dst_path = os.path.join(scripts_dst, name)
            shutil.copy2(src, dst_path)
            if name.endswith('.sh'):
                try:
                    os.chmod(dst_path, 0o755)
                except Exception:
                    pass
            logger.info("已复制 %s -> %s", name, scripts_dst)


def refresh_instance_env_and_scripts(instance_id):
    """刷新已存在实例的 .apk-site-env（含当前 APKSITE_BASE_URL）与 scripts，便于通知用对下载地址和脚本逻辑。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False
    jenkins_home = inst.get('jenkins_home') or ''
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return False
    output_base = get_instance_output_base(inst)
    _write_instance_env_and_scripts(
        jenkins_home,
        inst.get('port'),
        inst.get('task_name') or '',
        output_base,
        inst.get('feishu_webhook') or '',
        inst.get('build_defaults')
    )
    return True


def sync_instance_job_config(instance_id):
    """根据实例的 build_defaults 重新生成并写入 Android job config.xml 与 unity_paths.json。用于编辑实例参数后同步到 Jenkins。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False
    jenkins_home = inst.get('jenkins_home') or ''
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return False
    job_dir = os.path.join(jenkins_home, 'jobs', 'Android')
    build_defaults = inst.get('build_defaults') or {}
    output_base = get_instance_output_base(inst)
    try:
        content = _generate_job_config_xml(output_base, build_defaults)
        config_path = os.path.join(job_dir, 'config.xml')
        os.makedirs(job_dir, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)
        unity_versions = build_defaults.get('unity_versions') or []
        if False and isinstance(unity_versions, list) and unity_versions:
            paths = {}
            for u in unity_versions:
                if isinstance(u, dict) and u.get('version'):
                    paths[str(u.get('version', '')).strip()] = (u.get('path') or '').strip()
            if paths:
                paths_file = os.path.join(jenkins_home, 'unity_paths.json')
                with open(paths_file, 'w', encoding='utf-8') as f:
                    f.write('')
        logger.info("已同步 Jenkins 任务配置: %s", job_dir)
        return True
    except Exception as e:
        logger.warning("同步 Jenkins 任务配置失败: %s", e)
        return False


def start_jenkins(port, started_by='', task_name='', feishu_webhook='', build_defaults=None):
    """启动一个 Jenkins 实例。task_name 用于区分任务并作为输出子目录；feishu_webhook 为该实例飞书通知地址；
    build_defaults 为可选默认构建参数（app_name, version_name, version_code, unity_versions, output_base_dir, git_url, git_branches, git_ssh_key_path 等）。"""
    ok, msg = check_port(port)
    if not ok:
        return (False, None, msg)
    port = int(port)
    task_name = (task_name or '').strip()
    feishu_webhook = (feishu_webhook or '').strip()
    war = get_jenkins_war_path()
    if not war:
        return (False, None, "未找到 jenkins.war。请在 .env 中设置 JENKINS_WAR_PATH 或将 war 放到 data/jenkins_instances/jenkins.war")
    jenkins_home = os.path.join(INSTANCES_DIR, str(port))
    os.makedirs(jenkins_home, exist_ok=True)
    output_base = get_instance_output_base({'task_name': task_name, 'port': port, 'build_defaults': build_defaults or {}})
    # 注入固定管理员脚本并跳过安装向导
    _write_jenkins_init_admin_script(jenkins_home, Config.JENKINS_DEFAULT_USER, Config.JENKINS_DEFAULT_PASSWORD)
    # 复制 Android 任务（含 build_defaults 时生成下拉与默认值）
    _copy_android_job_to_jenkins_home(jenkins_home, port=port, task_name=task_name, build_defaults=build_defaults)
    # 写入 .apk-site-env 与（可选）.apk-site-feishu，并复制通知脚本，修复通知脚本路径
    _write_instance_env_and_scripts(jenkins_home, port, task_name, output_base, feishu_webhook, build_defaults)
    instances = load_jenkins_instances()
    for inst in instances:
        if inst.get('port') == port and inst.get('status') == 'running':
            if _is_process_alive(inst.get('pid')):
                return (False, None, "端口 %s 上已有运行中的 Jenkins" % port)
    # 启动进程：跳过安装向导；标准输出/错误写入实例日志便于排查
    env = os.environ.copy()
    env['JENKINS_HOME'] = jenkins_home
    logs_dir = os.path.join(jenkins_home, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, 'jenkins.log')
    java_args = ['java', '-Djenkins.install.runSetupWizard=false', '-jar', war, '--httpPort=%d' % port]
    try:
        with open(log_path, 'a', encoding='utf-8', errors='replace') as log_file:
            proc = subprocess.Popen(
                java_args,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(war),
                start_new_session=True
            )
    except FileNotFoundError:
        return (False, None, "未找到 java 命令，请先安装 JDK 并加入 PATH")
    except Exception as e:
        return (False, None, str(e))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    instance_id = str(uuid.uuid4())[:8]
    new_inst = {
        'id': instance_id,
        'port': port,
        'task_name': task_name,
        'feishu_webhook': feishu_webhook,
        'build_defaults': build_defaults or {},
        'status': 'running',
        'pid': proc.pid,
        'jenkins_home': jenkins_home,
        'added_at': now,
        'added_by': started_by,
        'started_at': now,
        'started_by': started_by,
        'default_creds': True,
    }
    instances.append(new_inst)
    save_jenkins_instances(instances)
    return (True, instance_id, None)


def stop_jenkins(instance_id=None, port=None):
    """停止 Jenkins。按 instance_id 或 port 查找。返回 (success, error_message)。"""
    instances = load_jenkins_instances()
    target = None
    for i, inst in enumerate(instances):
        if (instance_id and inst.get('id') == instance_id) or (port is not None and inst.get('port') == int(port)):
            target = (i, inst)
            break
    if not target:
        return (False, "未找到该实例")
    idx, inst = target
    pid = inst.get('pid')
    if pid and _is_process_alive(pid):
        try:
            if sys.platform == 'win32':
                subprocess.run(['taskkill', '/F', '/PID', str(pid)], timeout=5, capture_output=True)
            else:
                os.kill(pid, 15)
            inst['status'] = 'stopped'
            inst['pid'] = None
            instances[idx] = inst
            save_jenkins_instances(instances)
            return (True, None)
        except Exception as e:
            return (False, str(e))
    inst['status'] = 'stopped'
    inst['pid'] = None
    instances[idx] = inst
    save_jenkins_instances(instances)
    return (True, None)


def start_existing_jenkins(instance_id, started_by=''):
    """启动已存在且当前已停止的 Jenkins 实例。返回 (success, error_message)。"""
    instances = load_jenkins_instances()
    target = None
    for i, inst in enumerate(instances):
        if inst.get('id') == instance_id:
            target = (i, inst)
            break
    if not target:
        return (False, "未找到该实例")
    idx, inst = target
    if inst.get('status') == 'running' and _is_process_alive(inst.get('pid')):
        return (False, "该实例已在运行中")
    port = inst.get('port')
    if port is None:
        return (False, "实例缺少端口信息")
    port = int(port)
    ok, msg = check_port(port)
    if not ok:
        return (False, msg)
    jenkins_home = (inst.get('jenkins_home') or '').strip()
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return (False, "实例的 JENKINS_HOME 不存在: %s" % (jenkins_home or "(空)"))
    war = get_jenkins_war_path()
    if not war:
        return (False, "未找到 jenkins.war，请在 .env 中设置 JENKINS_WAR_PATH")
    env = os.environ.copy()
    env['JENKINS_HOME'] = jenkins_home
    logs_dir = os.path.join(jenkins_home, 'logs')
    os.makedirs(logs_dir, exist_ok=True)
    log_path = os.path.join(logs_dir, 'jenkins.log')
    java_args = ['java', '-Djenkins.install.runSetupWizard=false', '-jar', war, '--httpPort=%d' % port]
    try:
        with open(log_path, 'a', encoding='utf-8', errors='replace') as log_file:
            proc = subprocess.Popen(
                java_args,
                env=env,
                stdout=log_file,
                stderr=subprocess.STDOUT,
                cwd=os.path.dirname(war),
                start_new_session=True
            )
    except FileNotFoundError:
        return (False, "未找到 java 命令，请先安装 JDK 并加入 PATH")
    except Exception as e:
        return (False, str(e))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    inst['status'] = 'running'
    inst['pid'] = proc.pid
    inst['started_at'] = now
    inst['started_by'] = started_by
    instances[idx] = inst
    save_jenkins_instances(instances)
    return (True, None)


def delete_jenkins_instance(instance_id=None, port=None):
    """从列表删除实例（先停止再删）。返回 (success, error_message)。"""
    success, err = stop_jenkins(instance_id=instance_id, port=port)
    if not success and err != "未找到该实例":
        return (success, err)
    instances = load_jenkins_instances()
    if instance_id:
        instances = [i for i in instances if i.get('id') != instance_id]
    elif port is not None:
        instances = [i for i in instances if i.get('port') != int(port)]
    else:
        return (False, "请指定 instance_id 或 port")
    save_jenkins_instances(instances)
    return (True, None)


def update_instance(instance_id, task_name=None, feishu_webhook=None, build_defaults=None):
    """更新实例的 task_name、feishu_webhook、build_defaults。返回 (success, error_message)。"""
    instances = load_jenkins_instances()
    for i, inst in enumerate(instances):
        if inst.get('id') == instance_id:
            if task_name is not None:
                inst['task_name'] = str(task_name).strip()
            if feishu_webhook is not None:
                inst['feishu_webhook'] = str(feishu_webhook).strip()
            if build_defaults is not None:
                inst['build_defaults'] = build_defaults if isinstance(build_defaults, dict) else {}
            save_jenkins_instances(instances)
            return (True, None)
    return (False, "未找到该实例")


def list_instances():
    """返回实例列表，并刷新运行状态。"""
    instances = load_jenkins_instances()
    for inst in instances:
        pid = inst.get('pid')
        if pid and _is_process_alive(pid):
            inst['status'] = 'running'
        else:
            # 可能被外部杀掉，再按端口检查
            p = inst.get('port')
            found_pid = _get_pid_by_port(p) if p else None
            if found_pid:
                inst['pid'] = found_pid
                inst['status'] = 'running'
            else:
                inst['status'] = 'stopped'
                inst['pid'] = None
    save_jenkins_instances(instances)
    return instances


def get_instance_by_id(instance_id):
    for inst in load_jenkins_instances():
        if inst.get('id') == instance_id:
            return inst
    return None


def enrich_build_defaults_from_disk(inst):
    """从实例的 .apk-site-env 与 jobs/Android/config.xml 读取实际配置，回填到 inst['build_defaults'] 中缺失的项，便于编辑页显示完整。"""
    if not inst:
        return
    jenkins_home = (inst.get('jenkins_home') or '').strip()
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return
    bd = inst.get('build_defaults')
    if not isinstance(bd, dict):
        bd = {}
        inst['build_defaults'] = bd

    env_path = os.path.join(jenkins_home, '.apk-site-env')
    if os.path.isfile(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8', errors='replace') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'):
                        continue
                    if line.startswith('export '):
                        rest = line[7:].strip()
                        if '=' in rest:
                            key, _, val = rest.partition('=')
                            key = key.strip()
                            val = val.strip().strip('"').strip("'").strip()
                            if key == 'GIT_URL' and not bd.get('git_url'):
                                bd['git_url'] = val
                            elif key == 'GIT_SSH_KEY_PATH' and not bd.get('git_ssh_key_path'):
                                bd['git_ssh_key_path'] = val
                            elif key == 'GIT_WORKSPACE' and not bd.get('git_workspace'):
                                bd['git_workspace'] = val
                            elif key == 'APK_DIR' and not bd.get('output_base_dir'):
                                bd['output_base_dir'] = val
        except Exception as e:
            logger.debug("读取 .apk-site-env 失败: %s", e)

    config_path = os.path.join(jenkins_home, 'jobs', 'Android', 'config.xml')
    if os.path.isfile(config_path):
        try:
            import re
            with open(config_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read()
            def get_param_default(name):
                m = re.search(r'<name>%s</name>.*?<defaultValue>([^<]*)</defaultValue>' % re.escape(name), content, re.DOTALL)
                return m.group(1).strip() if m else None
            def get_choice_options(name):
                m = re.search(r'<name>%s</name>.*?<a class="string-array">(.*?)</a></choices>' % re.escape(name), content, re.DOTALL)
                if not m:
                    return []
                return re.findall(r'<string>([^<]*)</string>', m.group(1))
            if not bd.get('app_name'):
                v = get_param_default('APP_NAME')
                if v:
                    bd['app_name'] = v
            if not bd.get('version_name'):
                v = get_param_default('VERSION_NAME')
                if v:
                    bd['version_name'] = v
            if not bd.get('version_code'):
                v = get_param_default('VERSION_CODE')
                if v:
                    bd['version_code'] = v
            if not bd.get('output_base_dir'):
                v = get_param_default('OUTPUT_BASE_DIR')
                if v:
                    bd['output_base_dir'] = v
            unity_choices = get_choice_options('UNITY_VERSION')
            if unity_choices and not bd.get('unity_versions'):
                bd['unity_versions'] = [{'version': c, 'path': ''} for c in unity_choices]
            branch_choices = get_choice_options('GIT_BRANCH')
            if branch_choices and not bd.get('git_branches'):
                bd['git_branches'] = branch_choices
            if branch_choices and not bd.get('default_git_branch'):
                bd['default_git_branch'] = branch_choices[0]
        except Exception as e:
            logger.debug("解析 config.xml 失败: %s", e)

    # 从 unity_paths.json 补全 Unity 版本对应的安装路径
    paths_file = os.path.join(jenkins_home, 'unity_paths.json')
    paths_file = ''
    if False and os.path.isfile(paths_file) and bd.get('unity_versions'):
        try:
            with open(paths_file, 'r', encoding='utf-8') as f:
                paths_map = {}
            if isinstance(paths_map, dict):
                for u in bd['unity_versions']:
                    if isinstance(u, dict) and not (u.get('path') or '').strip():
                        p = paths_map.get((u.get('version') or '').strip())
                        if p:
                            u['path'] = p
        except Exception as e:
            logger.debug("读取 unity_paths.json 失败: %s", e)

    # 仍无 path 时，尝试本机常见 Unity 安装路径（Mac: Hub）
    if bd.get('unity_versions'):
        for u in bd['unity_versions']:
            if not isinstance(u, dict) or (u.get('path') or '').strip():  # 已有 path 则跳过
                continue
            ver = (u.get('version') or '').strip()
            if not ver:
                continue
            candidates = [
                os.path.join('/Applications/Unity/Hub/Editor', ver, 'Unity.app'),
                os.path.expanduser(os.path.join('~/Applications/Unity/Hub/Editor', ver, 'Unity.app')),
            ]
            for p in candidates:
                if os.path.isdir(p) or os.path.isfile(p):
                    u['path'] = p
                    break


def get_instance_by_port(port):
    for inst in load_jenkins_instances():
        if inst.get('port') == int(port):
            return inst
    return None


def get_jenkins_url_for_instance(instance_id=None, port=None):
    """返回实例的 Jenkins 根 URL。"""
    if port is not None:
        return 'http://127.0.0.1:%d' % int(port)
    inst = get_instance_by_id(instance_id) if instance_id else None
    if inst:
        return 'http://127.0.0.1:%d' % inst.get('port', 8080)
    return None


def get_builds_dir_for_instance(instance_id=None, port=None):
    """返回该实例的 Android job 构建目录。"""
    inst = None
    if instance_id:
        inst = get_instance_by_id(instance_id)
    elif port is not None:
        inst = get_instance_by_port(port)
    if inst and inst.get('jenkins_home'):
        return os.path.join(inst['jenkins_home'], 'jobs', Config.JENKINS_JOB_NAME, 'builds')
    return None
