# -*- coding: utf-8 -*-
from __future__ import annotations
"""Jenkins 多实例管理：端口检测、启动/停止、环境检查与一键部署、实例默认构建参数"""

import os
import sys
import socket
import subprocess
import platform
import uuid
import logging
import shutil
import urllib.request
from datetime import datetime
try:
    import winreg
except Exception:
    winreg = None

from config import Config, JENKINS_CLONE_DIR
from models.data import load_jenkins_instances, save_jenkins_instances, channels_db

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
    raise FileNotFoundError(
        'jenkins-clone-overlay not found, checked: %s' % ', '.join(candidates)
    )


def _resolve_java_bin():
    """Return a usable java executable path/command, or None if not found."""
    # 1) Directly available in PATH
    try:
        p = subprocess.run(['java', '-version'], capture_output=True, timeout=5)
        if p.returncode == 0:
            return 'java'
    except Exception:
        pass

    # 2) JAVA_HOME
    java_home = (os.environ.get('JAVA_HOME') or '').strip().strip('"')
    if java_home:
        cand = os.path.join(java_home, 'bin', 'java.exe' if sys.platform == 'win32' else 'java')
        if os.path.isfile(cand):
            return cand

    # 3) Common install locations on Windows
    if sys.platform == 'win32':
        roots = [
            os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Java'),
            os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), 'Eclipse Adoptium'),
            os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Java'),
            os.path.join(os.environ.get('ProgramFiles(x86)', r'C:\Program Files (x86)'), 'Eclipse Adoptium'),
        ]
        candidates = []
        for root in roots:
            if not root or not os.path.isdir(root):
                continue
            try:
                for d in os.listdir(root):
                    java_exe = os.path.join(root, d, 'bin', 'java.exe')
                    if os.path.isfile(java_exe):
                        candidates.append(java_exe)
            except Exception:
                continue
        # Prefer higher version-like folder names
        candidates = sorted(candidates, reverse=True)
        if candidates:
            return candidates[0]

        # 4) Windows registry (JDK/JRE InstallPath)
        if winreg is not None:
            reg_keys = [
                r"SOFTWARE\JavaSoft\JDK",
                r"SOFTWARE\JavaSoft\Java Development Kit",
                r"SOFTWARE\JavaSoft\JRE",
                r"SOFTWARE\Eclipse Adoptium\JDK",
                r"SOFTWARE\WOW6432Node\JavaSoft\JDK",
                r"SOFTWARE\WOW6432Node\JavaSoft\Java Development Kit",
                r"SOFTWARE\WOW6432Node\JavaSoft\JRE",
            ]
            for key_path in reg_keys:
                try:
                    with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, key_path) as key:
                        i = 0
                        while True:
                            try:
                                ver = winreg.EnumKey(key, i)
                                i += 1
                            except OSError:
                                break
                            try:
                                with winreg.OpenKey(key, ver) as sub:
                                    install_path, _ = winreg.QueryValueEx(sub, "JavaHome")
                                    cand = os.path.join(install_path, "bin", "java.exe")
                                    if os.path.isfile(cand):
                                        return cand
                            except OSError:
                                continue
                except OSError:
                    continue

    return None


def _xml_esc(s):
    if s is None:
        return ''
    s = str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;').replace('"', '&quot;')
    return s


def _build_param_defs_xml(build_defaults, output_base, instance_type='general'):
    """根据实例的 build_defaults 生成 Jenkins 任务 parameterDefinitions 的 XML 片段。
    instance_type='commercial' 时额外包含商业级热更发布参数。"""
    d = build_defaults or {}
    app_name = (d.get('app_name') or '').strip() or 'GameKu'
    version_name = (d.get('version_name') or '').strip() or '1.0.0'
    version_code = (d.get('version_code') or '').strip() or '1'
    out_dir = (d.get('output_base_dir') or '').strip() or output_base
    unity_versions = d.get('unity_versions') or []
    if not isinstance(unity_versions, list) or not unity_versions:
        try:
            from services.unity_version_catalog_service import resolve_unity_versions_for_build
            unity_versions = resolve_unity_versions_for_build(d)
        except Exception:
            unity_versions = []
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
    lines = []
    if instance_type == 'commercial':
        lines.extend([
            '<hudson.model.StringParameterDefinition>',
            '  <name>UNITY_VERSION</name><description>Unity 版本（由版本配置传入，见 unity_paths.json）</description>',
            '  <defaultValue>%s</defaultValue><trim>true</trim>' % _xml_esc(default_unity),
            '</hudson.model.StringParameterDefinition>',
        ])
    else:
        lines.extend([
            '<hudson.model.ChoiceParameterDefinition>',
            '  <name>UNITY_VERSION</name>',
            '  <description>Unity 版本（对应安装路径见 JENKINS_HOME/unity_paths.json）</description>',
            '  <choices class="java.util.Arrays$ArrayList"><a class="string-array">',
        ])
        for c in unity_choices:
            lines.append('    <string>%s</string>' % _xml_esc(c))
        lines.extend([
            '  </a></choices>',
            '</hudson.model.ChoiceParameterDefinition>',
        ])
    lines.extend([
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
    ])
    branch_default = default_branch or (git_branches[0] if git_branches else 'main')
    lines.extend([
        '<hudson.model.StringParameterDefinition>',
        '  <name>GIT_BRANCH</name><description>Git 分支（由版本配置传入，任意分支名）</description>',
        '  <defaultValue>%s</defaultValue><trim>true</trim>' % _xml_esc(branch_default),
        '</hudson.model.StringParameterDefinition>',
        '<hudson.model.StringParameterDefinition>',
        '  <name>UNITY_PROJECT_PATH</name><description>Unity 项目目录（可选；未填则自动从 GIT_WORKSPACE 探测 Assets/Editor）</description><defaultValue></defaultValue><trim>true</trim>',
        '</hudson.model.StringParameterDefinition>',
    ])
    channel_ids = ['dev', 'test', 'production']
    if isinstance(channels_db, list) and channels_db:
        channel_ids = [(c.get('id') or '').strip() for c in channels_db if (c.get('id') or '').strip()]
    channel_default = (channel_ids[0] if channel_ids else '')
    lines.extend([
        '<hudson.model.StringParameterDefinition>',
        '  <name>CHANNEL</name>',
        '  <description>渠道 ID（如 wechat、dev；与 RELEASE_CHANNEL 配合，任意渠道名）</description>',
        '  <defaultValue>%s</defaultValue><trim>true</trim>' % _xml_esc(channel_default),
        '</hudson.model.StringParameterDefinition>',
    ])
    # ============ 版本流水线参数（仅 commercial 实例）============
    if instance_type == 'commercial':
        # Step 1: 配置导出发布
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>CONFIG_EXPORT_ENABLED</name>')
        lines.append('      <description>Step1 配置导出: true / false</description>')
        lines.append('      <defaultValue>true</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>CONFIG_ENVIRONMENT</name>')
        lines.append('      <description>配置导出环境: Development / Testing / Staging / Production</description>')
        lines.append('      <defaultValue>Development</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>CONFIG_PLATFORM</name>')
        lines.append('      <description>配置导出平台: Android / iOS / Windows</description>')
        lines.append('      <defaultValue>Android</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>CONFIG_CLIENT_VERSION</name>')
        lines.append('      <description>配置导出客户端版本</description>')
        lines.append('      <defaultValue>1.0.0</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>CONFIG_REMOTE_PREFIX</name>')
        lines.append('      <description>配置远端路径前缀</description>')
        lines.append('      <defaultValue>config-release</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>CONFIG_INCLUDE_CODE</name>')
        lines.append('      <description>配置导出包含代码: true / false</description>')
        lines.append('      <defaultValue>false</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        # Step 2: 资源打包
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RESOURCE_BUILD_ENABLED</name>')
        lines.append('      <description>Step2 资源打包: true / false</description>')
        lines.append('      <defaultValue>true</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RESOURCE_PROVIDER</name>')
        lines.append('      <description>资源打包引擎: addressables-v2 / legacy-bundle-builder</description>')
        lines.append('      <defaultValue>addressables-v2</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RESOURCE_SCENARIO</name>')
        lines.append('      <description>资源打包场景方案</description>')
        lines.append('      <defaultValue>default</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        # Step 3: 热更发布
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>HOT_RELEASE_ENABLED</name>')
        lines.append('      <description>Step3 热更发布: true / false</description>')
        lines.append('      <defaultValue>true</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_VERSION</name>')
        lines.append('      <description>热更版本号</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_ENVIRONMENT</name>')
        lines.append('      <description>热更环境</description>')
        lines.append('      <defaultValue>Development</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_CHANNEL</name>')
        lines.append('      <description>热更渠道</description>')
        lines.append('      <defaultValue>common</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_PLATFORM</name>')
        lines.append('      <description>热更平台</description>')
        lines.append('      <defaultValue>Android</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_TARGETS</name>')
        lines.append('      <description>热更目标: code,resource</description>')
        lines.append('      <defaultValue>code,resource</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_HOT_LABELS</name>')
        lines.append('      <description>热更标签</description>')
        lines.append('      <defaultValue>hotupdate,aotmeta</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_UPLOAD_MODE</name>')
        lines.append('      <description>上传模式: incremental / full</description>')
        lines.append('      <defaultValue>incremental</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_MODE</name>')
        lines.append('      <description>发布模式: build-upload / build / upload / activate / rollback</description>')
        lines.append('      <defaultValue>build-upload</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_PLAN_FILE</name>')
        lines.append('      <description>发布计划 JSON 文件绝对路径（由后台生成）</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_UPLOAD</name>')
        lines.append('      <description>是否上传: true / false</description>')
        lines.append('      <defaultValue>true</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_ACTIVATE</name>')
        lines.append('      <description>上传后是否激活: true / false</description>')
        lines.append('      <defaultValue>false</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>COMMERCIAL_RESULT_OUT</name>')
        lines.append('      <description>商业发布结果输出文件路径</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>COMMERCIAL_AUTOMATION_OUT</name>')
        lines.append('      <description>商业发布自动化计划输出文件路径</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_CODE_COMPRESSION</name>')
        lines.append('      <description>代码包压缩: Zip / None / Lz4</description>')
        lines.append('      <defaultValue>Zip</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_CODE_ENCRYPTION</name>')
        lines.append('      <description>代码包加密: Aes / None / Xor</description>')
        lines.append('      <defaultValue>Aes</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_CODE_SIGNATURE</name>')
        lines.append('      <description>代码包签名: builtin-signature / 空</description>')
        lines.append('      <defaultValue>builtin-signature</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_CODE_UNITS</name>')
        lines.append('      <description>代码包单元</description>')
        lines.append('      <defaultValue>aotmeta, hotupdate, scriptpatch, symbols</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_RESOURCE_COMPRESSION</name>')
        lines.append('      <description>资源包压缩: Zip / None / Lz4</description>')
        lines.append('      <defaultValue>None</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_RESOURCE_ENCRYPTION</name>')
        lines.append('      <description>资源包加密: Aes / None</description>')
        lines.append('      <defaultValue>None</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_RESOURCE_SIGNATURE</name>')
        lines.append('      <description>资源包签名: builtin-signature / 空</description>')
        lines.append('      <defaultValue>builtin-signature</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_RESOURCE_UNITS</name>')
        lines.append('      <description>资源包单元</description>')
        lines.append('      <defaultValue>addressable, hotupdate, optional, platform, hd, streaming</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_COMPRESSION_OVERRIDE</name>')
        lines.append('      <description>压缩覆盖</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_ENCRYPTION_OVERRIDE</name>')
        lines.append('      <description>加密覆盖</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_SIGNATURE_OVERRIDE</name>')
        lines.append('      <description>签名覆盖</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RELEASE_ROLLBACK_TARGET</name>')
        lines.append('      <description>回滚目标版本</description>')
        lines.append('      <defaultValue></defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        # Step 4: APK打包
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>APK_BUILD_ENABLED</name>')
        lines.append('      <description>Step4 APK打包: true / false</description>')
        lines.append('      <defaultValue>true</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
        lines.append('    <hudson.model.StringParameterDefinition>')
        lines.append('      <name>RUN_BASE_APK_BUILD_FIRST</name>')
        lines.append('      <description>是否先执行传统 build_gameku_android.sh（商业建议 false）</description>')
        lines.append('      <defaultValue>false</defaultValue>')
        lines.append('      <trim>true</trim>')
        lines.append('    </hudson.model.StringParameterDefinition>')
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
    """?? Jenkins ??????? {java: {ok, version, path}, git: {ok, version}, war: {ok, path}}?"""
    result = {'java': {'ok': False, 'version': '', 'path': ''}, 'git': {'ok': False, 'version': ''}, 'war': {'ok': False, 'path': ''}}
    # Java
    try:
        java_bin = _resolve_java_bin()
        if not java_bin:
            raise FileNotFoundError('java not found')
        out = subprocess.check_output([java_bin, '-version'], stderr=subprocess.STDOUT, timeout=5)
        text_out = (out or b'').decode(errors='ignore')
        result['java']['ok'] = True
        result['java']['path'] = java_bin
        for line in text_out.splitlines():
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
    """返回当前平台的一键部署说明（仅展示）。"""
    if platform_name in ('darwin', 'mac', 'macos'):
        return '''# Mac 部署 Jenkins 环境
# 1. 安装 Java（若未安装）
brew install openjdk@17  # 或 brew install openjdk@11
# 2. 下载 Jenkins war（可选，本系统也会自动使用已配置的 JENKINS_WAR_PATH）
# curl -L -o jenkins.war https://get.jenkins.io/war-stable/latest/jenkins.war
'''
    if platform_name in ('win32', 'windows'):
        return '''# Windows 部署 Jenkins 环境
# 优先点击上方“执行部署并查看日志”自动完成检测/安装。
# 若自动部署失败，再手动执行：
# 1. 安装 Java：从 https://adoptium.net/ 下载并安装 JDK 17+
# 2. 或将 Jenkins war 路径配置到环境变量 JENKINS_WAR_PATH
# 下载 war: https://get.jenkins.io/war-stable/latest/jenkins.war
'''
    return "# 当前平台: %s\n# 请手动安装 Java 并配置 JENKINS_WAR_PATH\n" % platform_name


def run_deploy_env(log_path):
    """执行环境部署并持续写日志。支持 macOS / Windows 自动化步骤。"""
    import threading

    def _download_war_if_missing(f):
        war_path = get_jenkins_war_path()
        if war_path and os.path.isfile(war_path):
            f.write("Jenkins war 已就绪: %s\n" % war_path)
            return True
        target = os.path.join(INSTANCES_DIR, 'jenkins.war')
        url = 'https://get.jenkins.io/war-stable/latest/jenkins.war'
        f.write("未检测到 jenkins.war，尝试下载: %s\n" % url)
        f.flush()
        try:
            os.makedirs(INSTANCES_DIR, exist_ok=True)
            urllib.request.urlretrieve(url, target)
            f.write("下载完成: %s\n" % target)
            return True
        except Exception as de:
            f.write("下载失败: %s\n" % de)
            return False

    def _run():
        with open(log_path, 'w', encoding='utf-8') as f:
            f.write("开始时间: %s\n" % datetime.now().isoformat())
            f.write("平台: %s\n" % platform.system())
            try:
                if sys.platform == 'darwin':
                    f.write("macOS 一键部署开始...\n")
                    java_bin = _resolve_java_bin()
                    if java_bin:
                        f.write("已检测到 Java: %s\n" % java_bin)
                    else:
                        brew = shutil.which('brew')
                        if brew:
                            cmd = [brew, 'install', 'openjdk@17']
                            f.write("未检测到 Java，执行命令: %s\n" % ' '.join(cmd))
                            f.flush()
                            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                            for line in p.stdout:
                                f.write(line)
                                f.flush()
                            p.wait()
                            f.write("brew 退出码: %s\n" % p.returncode)
                        else:
                            f.write("未找到 brew，无法自动安装 JDK。\n")
                        java_bin = _resolve_java_bin()
                        if java_bin:
                            f.write("安装后检测到 Java: %s\n" % java_bin)
                        else:
                            f.write("仍未检测到 Java。请手动安装 JDK 17+ 并配置 JAVA_HOME/PATH。\n")
                    _download_war_if_missing(f)

                elif sys.platform == 'win32':
                    f.write("Windows 一键部署开始...\n")
                    java_bin = _resolve_java_bin()
                    if java_bin:
                        f.write("已检测到 Java: %s\n" % java_bin)
                    else:
                        winget_path = shutil.which('winget')
                        if winget_path:
                            cmd = [winget_path, 'install', '--id', 'EclipseAdoptium.Temurin.17.JDK', '-e', '--silent', '--accept-package-agreements', '--accept-source-agreements']
                            f.write("未检测到 Java，执行命令: %s\n" % ' '.join(cmd))
                            f.flush()
                            p = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
                            for line in p.stdout:
                                f.write(line)
                                f.flush()
                            p.wait()
                            f.write("winget 退出码: %s\n" % p.returncode)
                        else:
                            f.write("未找到 winget，无法自动安装 JDK。\n")
                        java_bin = _resolve_java_bin()
                        if java_bin:
                            f.write("安装后检测到 Java: %s\n" % java_bin)
                        else:
                            f.write("仍未检测到 Java。请手动安装 JDK 17+ 并配置 JAVA_HOME/PATH。\n")
                    _download_war_if_missing(f)

                else:
                    f.write("当前平台暂不支持自动部署，请手动安装 Java/Jenkins war。\n")
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


def _copy_android_job_to_jenkins_home(jenkins_home, port=None, task_name=None, build_defaults=None, instance_type='general'):
    """把 overlay 里的 Android 任务复制到新实例的 JENKINS_HOME；OUTPUT_BASE_DIR 按任务名/端口隔离。
    若提供 build_defaults，则生成带下拉与默认值的参数（Unity 版本、分支等），并写入 unity_paths.json。
    instance_type='commercial' 时额外包含商业级热更发布参数。"""
    try:
        job_dir = os.path.join(jenkins_home, 'jobs', 'Android')
        config_path = os.path.join(job_dir, 'config.xml')
        overlay_root = _resolve_overlay_root()
        config_src = os.path.join(overlay_root, 'jobs', 'Android', 'config.xml')
        if not os.path.isfile(config_src):
            return
        subdir = (task_name or '').strip() if (task_name and str(task_name).strip()) else ('jenkins_' + str(port or ''))
        output_base = os.path.join(Config.APK_DIR, subdir) if subdir else Config.APK_DIR
        builds_dir = os.path.join(job_dir, 'builds')
        os.makedirs(builds_dir, exist_ok=True)

        if build_defaults:
            content = _generate_job_config_xml(output_base, build_defaults, instance_type)
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
        if isinstance(unity_versions, list) and unity_versions:
            paths = {}
            for u in unity_versions:
                if isinstance(u, dict) and u.get('version'):
                    paths[str(u.get('version', '')).strip()] = (u.get('path') or '').strip()
            if paths:
                paths_file = os.path.join(jenkins_home, 'unity_paths.json')
                try:
                    with open(paths_file, 'w', encoding='utf-8') as f:
                        import json
                        json.dump(paths, f, ensure_ascii=False, indent=2)
                    logger.info("已写入 %s", paths_file)
                except Exception as e:
                    logger.warning("写入 unity_paths.json 失败: %s", e)

        logger.info("已写入 Android 任务到 %s（输出目录: %s）", job_dir, output_base)
    except Exception as e:
        logger.warning("复制 Android 任务失败: %s", e)


def _resolve_windows_git_bash():
    """Git for Windows bash.exe（Jenkins 以 SYSTEM 运行，不能依赖 PATH）。"""
    import winreg
    candidates = []
    try:
        with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, r'SOFTWARE\GitForWindows') as key:
            install_path, _ = winreg.QueryValueEx(key, 'InstallPath')
            if install_path:
                candidates.append(os.path.join(install_path, 'bin', 'bash.exe'))
    except OSError:
        pass
    for rel in (
        os.path.join('Program Files', 'Git', 'bin', 'bash.exe'),
        os.path.join('Git', 'bin', 'bash.exe'),
    ):
        candidates.append(os.path.join(os.environ.get('ProgramFiles', r'C:\Program Files'), rel.split(os.sep, 1)[-1]))
    candidates.append(r'E:\Git\bin\bash.exe')
    for path in candidates:
        if path and os.path.isfile(path):
            return path
    return ''


def _commercial_pipeline_builder_xml():
    """商业实例：config.xml 只 source 外置脚本，避免内嵌旧版 Step1（CommercialReleaseCli）。"""
    if os.name == 'nt':
        bash_exe = _resolve_windows_git_bash() or 'bash'
        cmd = (
            '@echo off\r\n'
            'chcp 65001 >nul\r\n'
            'set PYTHONIOENCODING=utf-8\r\n'
            'set "BASH=%s"\r\n'
            'if not exist "%%BASH%%" (\r\n'
            '  echo ERROR: Git bash not found: %%BASH%%\r\n'
            '  exit /b 1\r\n'
            ')\r\n'
            'if exist "%%JENKINS_HOME%%\\.apk-site-env" (\r\n'
            '  "%%BASH%%" -lc "set -a; source \\"%%JENKINS_HOME%%/.apk-site-env\\"; set +a"\r\n'
            ')\r\n'
            'if not exist "%%JENKINS_HOME%%\\scripts\\commercial_android_pipeline.sh" (\r\n'
            '  echo ERROR: missing pipeline script\r\n'
            '  exit /b 1\r\n'
            ')\r\n'
            '"%%BASH%%" "%%JENKINS_HOME%%\\scripts\\commercial_android_pipeline.sh"\r\n'
            'exit /b %%ERRORLEVEL%%\r\n'
        ) % bash_exe.replace('%', '%%')
        return (
            '  <builders>\n'
            '    <hudson.tasks.BatchFile>\n'
            '      <command>%s</command>\n'
            '      <configuredLocalRules/>\n'
            '    </hudson.tasks.BatchFile>\n'
            '  </builders>' % cmd
        )
    cmd = (
        '#!/bin/bash\n'
        'set -e\n'
        '[ -n "$JENKINS_HOME" ] &amp;&amp; [ -f "${JENKINS_HOME}/.apk-site-env" ] &amp;&amp; . "${JENKINS_HOME}/.apk-site-env"\n'
        'PIPELINE="${JENKINS_HOME}/scripts/commercial_android_pipeline.sh"\n'
        'if [ ! -f "$PIPELINE" ]; then\n'
        '  echo "ERROR: missing $PIPELINE"\n'
        '  exit 1\n'
        'fi\n'
        'exec bash "$PIPELINE"\n'
    )
    return (
        '  <builders>\n'
        '    <hudson.tasks.Shell>\n'
        '      <command>%s</command>\n'
        '      <configuredLocalRules/>\n'
        '    </hudson.tasks.Shell>\n'
        '  </builders>' % cmd
    )


def _generate_job_config_xml(output_base, build_defaults, instance_type='general'):
    """根据 output_base 与 build_defaults 生成完整 Android job config.xml 内容。"""
    overlay_root = _resolve_overlay_root()
    config_src = os.path.join(overlay_root, 'jobs', 'Android', 'config.xml')
    with open(config_src, 'r', encoding='utf-8') as f:
        content = f.read()
    param_xml = _build_param_defs_xml(build_defaults, output_base, instance_type)
    import re
    param_block = '<parameterDefinitions>\n%s\n      </parameterDefinitions>' % param_xml
    content = re.sub(
        r'<parameterDefinitions>.*?</parameterDefinitions>',
        lambda _m: param_block,
        content,
        count=1,
        flags=re.DOTALL,
    )
    content = content.replace('{{APK_DIR}}', output_base)
    if instance_type == 'commercial':
        builders_block = _commercial_pipeline_builder_xml()
        content = re.sub(
            r'<builders>.*?</builders>',
            lambda _m: builders_block,
            content,
            count=1,
            flags=re.DOTALL,
        )
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


def _write_instance_env_and_scripts(jenkins_home, port, task_name, output_base, feishu_webhook='', dingtalk_webhook='', build_defaults=None):
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
    # 兼容老实例：当本次 build_defaults 缺少 Git 配置时，尽量保留已有 .apk-site-env 中的值，避免“刷新后被清空”。
    existing_env = {}
    if os.path.isfile(env_path):
        try:
            with open(env_path, 'r', encoding='utf-8', errors='replace') as f:
                for raw in f:
                    line = raw.strip()
                    if not line or line.startswith('#') or not line.startswith('export '):
                        continue
                    rest = line[7:].strip()
                    if '=' not in rest:
                        continue
                    key, _, val = rest.partition('=')
                    existing_env[key.strip()] = val.strip().strip('"').strip("'").strip()
        except Exception:
            existing_env = {}

    bd = build_defaults or {}
    git_url = (bd.get('git_url') or '').strip() or (existing_env.get('GIT_URL') or '').strip()
    git_ssh_key_path = (bd.get('git_ssh_key_path') or '').strip() or (existing_env.get('GIT_SSH_KEY_PATH') or '').strip()
    git_workspace = (bd.get('git_workspace') or '').strip() or (existing_env.get('GIT_WORKSPACE') or '').strip()
    unity_project_path = (bd.get('unity_project_path') or '').strip() or (existing_env.get('UNITY_PROJECT_PATH') or '').strip()
    if git_url:
        lines.append('export GIT_URL="%s"' % esc(git_url))
    if git_ssh_key_path:
        lines.append('export GIT_SSH_KEY_PATH="%s"' % esc(git_ssh_key_path))
    if git_workspace:
        lines.append('export GIT_WORKSPACE="%s"' % esc(git_workspace))
    if unity_project_path:
        lines.append('export UNITY_PROJECT_PATH="%s"' % esc(unity_project_path))
    lines.append('export UNITY_PATH_MAP_FILE="%s"' % esc(os.path.join(jenkins_home, 'unity_paths.json')))
    lines.append('export UNITY_HUB="/Applications/Unity/Hub"')
    with open(env_path, 'w', encoding='utf-8') as f:
        f.write('\n'.join(lines) + '\n')
    logger.info("已写入 %s（APKSITE_BASE_URL=%s）", env_path, base_url)
    if (feishu_webhook or '').strip():
        feishu_path = os.path.join(jenkins_home, '.apk-site-feishu')
        webhook = (feishu_webhook or '').strip().replace('"', '\\"')
        with open(feishu_path, 'w', encoding='utf-8') as f:
            f.write('export FEISHU_WEBHOOK="%s"\n' % webhook)
        logger.info("已写入 %s", feishu_path)
    # 钉钉 webhook 写入 .apk-site-dingtalk
    if (dingtalk_webhook or '').strip():
        dingtalk_path = os.path.join(jenkins_home, '.apk-site-dingtalk')
        webhook = (dingtalk_webhook or '').strip().replace('"', '\\"')
        with open(dingtalk_path, 'w', encoding='utf-8') as f:
            f.write('export DINGTALK_WEBHOOK="%s"\n' % webhook)
        logger.info("已写入 %s", dingtalk_path)
    overlay_scripts = os.path.join(_resolve_overlay_root(), 'scripts')
    scripts_dst = os.path.join(jenkins_home, 'scripts')
    os.makedirs(scripts_dst, exist_ok=True)
    for name in ('jenkins_send_notify.sh', 'feishu_send.py', 'commercial_android_pipeline.sh'):
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
        inst.get('dingtalk_webhook') or '',
        inst.get('build_defaults')
    )
    return True


def _discover_unity_app_path(version):
    ver = (version or '').strip()
    if not ver:
        return ''
    candidates = [
        os.path.join('/Applications/Unity/Hub/Editor', ver, 'Unity.app'),
        os.path.expanduser(os.path.join('~/Applications/Unity/Hub/Editor', ver, 'Unity.app')),
    ]
    for p in candidates:
        if os.path.isdir(p) or os.path.isfile(p):
            return p
    return ''


def _write_unity_paths_json(jenkins_home, build_defaults):
    """写入 JENKINS_HOME/unity_paths.json，供构建脚本解析 Unity 安装路径。"""
    if not jenkins_home:
        return
    bd = build_defaults or {}
    try:
        from services.unity_version_catalog_service import resolve_unity_versions_for_build
        unity_versions = resolve_unity_versions_for_build(bd)
    except Exception:
        unity_versions = bd.get('unity_versions') or []
    paths = {}
    if isinstance(unity_versions, list):
        for u in unity_versions:
            if not isinstance(u, dict) or not (u.get('version') or '').strip():
                continue
            ver = str(u.get('version', '')).strip()
            p = (u.get('path') or '').strip() or _discover_unity_app_path(ver)
            if p:
                paths[ver] = p
    if not paths:
        default_ver = '6000.3.8f1'
        discovered = _discover_unity_app_path(default_ver)
        if discovered:
            paths[default_ver] = discovered
    if not paths:
        return
    paths_file = os.path.join(jenkins_home, 'unity_paths.json')
    try:
        import json
        with open(paths_file, 'w', encoding='utf-8') as f:
            json.dump(paths, f, ensure_ascii=False, indent=2)
        logger.info("已写入 %s", paths_file)
    except Exception as e:
        logger.warning("写入 unity_paths.json 失败: %s", e)


def _merge_build_defaults_for_plan(build_defaults: dict, plan: dict) -> dict:
    """把版本构建 plan 中的 git/unity 合并进实例 build_defaults（用于生成 Job 下拉）。"""
    bd = dict(build_defaults or {})
    plan = plan or {}
    gb = str(plan.get('gitBranch') or '').strip()
    branches = bd.get('git_branches') or ['main']
    if isinstance(branches, str):
        branches = [b.strip() for b in branches.splitlines() if b.strip()]
    if not isinstance(branches, list):
        branches = ['main']
    branches = [str(b).strip() for b in branches if str(b).strip()]
    if gb:
        if gb not in branches:
            branches.insert(0, gb)
        bd['default_git_branch'] = gb
    bd['git_branches'] = branches or ['main']

    uv = str(plan.get('unityVersion') or '').strip()
    try:
        from services.unity_version_catalog_service import resolve_unity_versions_for_build

        merged_uv = resolve_unity_versions_for_build(bd)
    except Exception:
        merged_uv = []
    if not isinstance(merged_uv, list):
        merged_uv = []
    if uv:
        seen = {str(x.get('version') or '').strip() for x in merged_uv if isinstance(x, dict)}
        if uv not in seen:
            path = ''
            up = str(plan.get('unityPath') or '').strip()
            if up:
                path = up
            else:
                try:
                    from services.unity_version_catalog_service import load_catalog

                    for ent in (load_catalog().get('entries') or []):
                        if isinstance(ent, dict) and str(ent.get('version') or '').strip() == uv:
                            path = str(ent.get('path') or '').strip()
                            break
                except Exception:
                    pass
            merged_uv.insert(0, {'version': uv, 'path': path})
    bd['unity_versions'] = merged_uv
    return bd


def reload_jenkins_job(instance_id, job_name='Android'):
    """通知 Jenkins 重新加载磁盘上的 config.xml。"""
    import json
    import http.cookiejar
    import urllib.request
    from services.jenkins import auth_header

    url = get_jenkins_url_for_instance(instance_id=instance_id)
    if not url:
        return False
    auth = auth_header(instance_id)
    cookie_jar = http.cookiejar.CookieJar()
    opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(cookie_jar))
    if auth:
        opener.addheaders.append(('Authorization', auth))

    def _open(req, timeout=15):
        return opener.open(req, timeout=timeout)

    crumb_header = None
    try:
        crumb_req = urllib.request.Request(url.rstrip('/') + '/crumbIssuer/api/json')
        with _open(crumb_req, timeout=10) as crumb_resp:
            if crumb_resp.getcode() == 200:
                crumb_data = json.loads(crumb_resp.read().decode())
                field = crumb_data.get('crumbRequestField') or 'Jenkins-Crumb'
                value = crumb_data.get('crumb', '')
                if value:
                    crumb_header = (field, value)
    except Exception:
        pass
    req = urllib.request.Request(
        '%s/job/%s/reload' % (url.rstrip('/'), job_name),
        method='POST',
    )
    if crumb_header:
        req.add_header(crumb_header[0], crumb_header[1])
    try:
        with _open(req) as resp:
            return resp.getcode() in (200, 201, 302)
    except Exception as exc:
        logger.warning('Jenkins reload job 失败: %s', exc)
        return False


def sync_instance_job_config(instance_id, build_defaults_override=None):
    """根据实例的 build_defaults 重新生成并写入 Android job config.xml 与 unity_paths.json。用于编辑实例参数后同步到 Jenkins。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False
    jenkins_home = resolve_jenkins_home(inst)
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return False
    job_dir = os.path.join(jenkins_home, 'jobs', 'Android')
    build_defaults = dict(inst.get('build_defaults') or {})
    if isinstance(build_defaults_override, dict):
        build_defaults.update(build_defaults_override)
    output_base = get_instance_output_base(inst)
    try:
        content = _generate_job_config_xml(output_base, build_defaults, inst.get('instance_type', 'general'))
        config_path = os.path.join(job_dir, 'config.xml')
        os.makedirs(job_dir, exist_ok=True)
        with open(config_path, 'w', encoding='utf-8') as f:
            f.write(content)
        _write_unity_paths_json(jenkins_home, build_defaults)
        logger.info("已同步 Jenkins 任务配置: %s", job_dir)
        return True
    except Exception as e:
        logger.warning("同步 Jenkins 任务配置失败: %s", e)
        return False


def prepare_instance_job_for_plan(instance_id, plan: dict) -> tuple[bool, str]:
    """触发商业构建前：把 plan 中的 GIT_BRANCH / UNITY_VERSION 写入 Job 参数定义并 reload。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False, 'Jenkins 实例不存在'
    bd = _merge_build_defaults_for_plan(inst.get('build_defaults') or {}, plan or {})
    if not sync_instance_job_config(instance_id, build_defaults_override=bd):
        return False, '同步 Jenkins Job 参数失败'
    if not reload_jenkins_job(instance_id):
        logger.warning(
            'Jenkins reload 未成功（常见 403）；若触发仍报 HTTP 500/Illegal choice，'
            '请在 Jenkins 管理中重启该实例一次以加载新 Job 参数。'
        )
    return True, ''


def start_jenkins(port, started_by='', task_name='', feishu_webhook='', dingtalk_webhook='', build_defaults=None, instance_type='general'):
    """启动一个 Jenkins 实例。支持飞书和钉钉多渠道通知。"""
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
    _copy_android_job_to_jenkins_home(jenkins_home, port=port, task_name=task_name, build_defaults=build_defaults, instance_type=instance_type)
    # 写入 .apk-site-env 与（可选）.apk-site-feishu，并复制通知脚本，修复通知脚本路径
    _write_instance_env_and_scripts(jenkins_home, port, task_name, output_base, feishu_webhook, dingtalk_webhook, build_defaults)
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
    java_bin = _resolve_java_bin()
    if not java_bin:
        return (False, None, "未找到 Java 可执行文件。请安装 JDK（建议 17+），并配置 JAVA_HOME 或加入 PATH")
    java_args = [java_bin, '-Dfile.encoding=UTF-8', '-Djenkins.install.runSetupWizard=false', '-jar', war, '--httpPort=%d' % port]
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
        return (False, None, "未找到 Java 可执行文件。请安装 JDK（建议 17+），并配置 JAVA_HOME 或加入 PATH")
    except Exception as e:
        return (False, None, str(e))
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    instance_id = str(uuid.uuid4())[:8]
    new_inst = {
        'id': instance_id,
        'port': port,
        'task_name': task_name,
        'feishu_webhook': feishu_webhook,
        'dingtalk_webhook': dingtalk_webhook,
        'instance_type': instance_type,
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
    jenkins_home = resolve_jenkins_home(inst)
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
    java_bin = _resolve_java_bin()
    if not java_bin:
        return (False, "未找到 Java 可执行文件。请安装 JDK（建议 17+），并配置 JAVA_HOME 或加入 PATH")
    java_args = [java_bin, '-Dfile.encoding=UTF-8', '-Djenkins.install.runSetupWizard=false', '-jar', war, '--httpPort=%d' % port]
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
        return (False, "未找到 Java 可执行文件。请安装 JDK（建议 17+），并配置 JAVA_HOME 或加入 PATH")
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


def update_instance(instance_id, task_name=None, feishu_webhook=None, dingtalk_webhook=None, build_defaults=None, instance_type=None):
    """更新实例的 task_name、webhooks、build_defaults、instance_type。"""
    instances = load_jenkins_instances()
    for i, inst in enumerate(instances):
        if inst.get('id') == instance_id:
            if task_name is not None:
                inst['task_name'] = str(task_name).strip()
            if feishu_webhook is not None:
                inst['feishu_webhook'] = str(feishu_webhook).strip()
            if dingtalk_webhook is not None:
                inst['dingtalk_webhook'] = str(dingtalk_webhook).strip()
            if build_defaults is not None:
                inst['build_defaults'] = build_defaults if isinstance(build_defaults, dict) else {}
            if instance_type is not None:
                inst['instance_type'] = str(instance_type).strip() or 'general'
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


def resolve_jenkins_home(inst):
    """实例记录里的 jenkins_home 可能是 Mac 路径；优先使用本机 INSTANCES_DIR/{port}。"""
    if not inst:
        return ''
    port = inst.get('port')
    if port is not None:
        local_home = os.path.join(INSTANCES_DIR, str(port))
        if os.path.isdir(local_home):
            return local_home
    jh = (inst.get('jenkins_home') or '').strip()
    if jh and os.path.isdir(jh):
        return jh
    if port is not None:
        return os.path.join(INSTANCES_DIR, str(port))
    return jh


def enrich_build_defaults_from_disk(inst):
    """从实例的 .apk-site-env 与 jobs/Android/config.xml 读取实际配置，回填到 inst['build_defaults'] 中缺失的项，便于编辑页显示完整。"""
    if not inst:
        return
    jenkins_home = resolve_jenkins_home(inst)
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
                            elif key == 'UNITY_PROJECT_PATH' and not bd.get('unity_project_path'):
                                bd['unity_project_path'] = val
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
    if os.path.isfile(paths_file) and bd.get('unity_versions'):
        try:
            with open(paths_file, 'r', encoding='utf-8') as f:
                import json
                paths_map = json.load(f)
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
    if inst:
        jenkins_home = resolve_jenkins_home(inst)
        if jenkins_home:
            return os.path.join(jenkins_home, 'jobs', Config.JENKINS_JOB_NAME, 'builds')
    return None
