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


def get_instance_output_base(inst, project_id=''):
    """返回该实例的默认构建输出根目录（与 job 内 OUTPUT_BASE_DIR 一致）。"""
    if not inst:
        return Config.APK_DIR
    out_dir = ''
    if project_id:
        try:
            from services.admin.project_build_config_service import get_project_build_config

            out_dir = (get_project_build_config(project_id).get('output_base_dir') or '').strip()
        except Exception:
            out_dir = ''
    if out_dir:
        return out_dir
    task_name = (inst.get('task_name') or '').strip()
    port = inst.get('port')
    subdir = task_name if task_name else ('jenkins_' + str(port) if port is not None else '')
    return os.path.join(Config.APK_DIR, subdir) if subdir else Config.APK_DIR


def _write_instance_env_and_scripts(
    jenkins_home,
    port,
    task_name,
    output_base,
    feishu_webhook='',
    dingtalk_webhook='',
    wecom_webhook='',
    build_defaults=None,
):
    """为管理内实例写入 .apk-site-env 与各渠道 webhook 文件，并复制通知脚本。"""
    from services import startup
    base_url = startup.get_canonical_base_url()  # 与启动横幅一致：局域网 IP:PORT
    env_path = os.path.join(jenkins_home, '.apk-site-env')
    job_builds = os.path.join(jenkins_home, 'jobs', 'Android', 'builds')
    from config import APK_SITE_ROOT
    apk_publish_dir = os.path.join(APK_SITE_ROOT, 'data', 'apk')
    apk_scan_dir = apk_publish_dir.replace('\\', '\\\\').replace('"', '\\"')
    apk_publish_esc = apk_publish_dir.replace('\\', '\\\\').replace('"', '\\"')
    def esc(s):
        return (s or '').replace('\\', '\\\\').replace('"', '\\"')
    lines = [
        '# 本实例环境，构建步骤会 source 此文件',
        'export JENKINS_CLONE="%s"' % esc(jenkins_home),
        'export APK_DIR="%s"' % esc(output_base),
        'export APK_SCAN_DIR="%s"' % apk_scan_dir,
        'export APK_PUBLISH_DIR="%s"' % apk_publish_esc,
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
    elif os.path.isfile(os.path.join(jenkins_home, '.apk-site-feishu')):
        try:
            os.remove(os.path.join(jenkins_home, '.apk-site-feishu'))
        except OSError:
            pass
    if (dingtalk_webhook or '').strip():
        dingtalk_path = os.path.join(jenkins_home, '.apk-site-dingtalk')
        webhook = (dingtalk_webhook or '').strip().replace('"', '\\"')
        with open(dingtalk_path, 'w', encoding='utf-8') as f:
            f.write('export DINGTALK_WEBHOOK="%s"\n' % webhook)
        logger.info("已写入 %s", dingtalk_path)
    elif os.path.isfile(os.path.join(jenkins_home, '.apk-site-dingtalk')):
        try:
            os.remove(os.path.join(jenkins_home, '.apk-site-dingtalk'))
        except OSError:
            pass
    if (wecom_webhook or '').strip():
        wecom_path = os.path.join(jenkins_home, '.apk-site-wecom')
        webhook = (wecom_webhook or '').strip().replace('"', '\\"')
        with open(wecom_path, 'w', encoding='utf-8') as f:
            f.write('export WECOM_WEBHOOK="%s"\n' % webhook)
        logger.info("已写入 %s", wecom_path)
    elif os.path.isfile(os.path.join(jenkins_home, '.apk-site-wecom')):
        try:
            os.remove(os.path.join(jenkins_home, '.apk-site-wecom'))
        except OSError:
            pass
    overlay_scripts = os.path.join(_resolve_overlay_root(), 'scripts')
    scripts_dst = os.path.join(jenkins_home, 'scripts')
    os.makedirs(scripts_dst, exist_ok=True)
    for name in (
        'jenkins_send_notify.sh',
        'feishu_send.py',
        'dingtalk_send.py',
        'wecom_send.py',
        'commercial_android_pipeline.sh',
        'archive_apk_after_build.py',
    ):
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
    jenkins_home = resolve_jenkins_home(inst)
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
        inst.get('wecom_webhook') or '',
        None,
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
    from services.unity_version_service import resolve_unity_app_path

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
            p = resolve_unity_app_path(ver, str(u.get('path') or '').strip())
            if p:
                paths[ver] = p
    if not paths:
        default_ver = '6000.3.8f1'
        discovered = resolve_unity_app_path(default_ver) or _discover_unity_app_path(default_ver)
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
            try:
                from services.unity_version_service import resolve_unity_app_path

                path = resolve_unity_app_path(uv, path) or path
            except Exception:
                pass
            merged_uv.insert(0, {'version': uv, 'path': path})
        else:
            for item in merged_uv:
                if isinstance(item, dict) and str(item.get('version') or '').strip() == uv:
                    try:
                        from services.unity_version_service import resolve_unity_app_path

                        resolved = resolve_unity_app_path(uv, str(item.get('path') or '').strip())
                        if resolved:
                            item['path'] = resolved
                    except Exception:
                        pass
                    break
    bd['unity_versions'] = merged_uv
    return bd


def _validate_plan_unity_installation(plan: dict) -> tuple[bool, str]:
    """构建前校验本机是否有所需 Unity 版本。"""
    plan = plan or {}
    uv = str(plan.get('unityVersion') or '').strip()
    if not uv:
        return True, ''
    try:
        from services.unity_version_service import detect_local_unity_installations, resolve_unity_app_path

        path = resolve_unity_app_path(uv, str(plan.get('unityPath') or '').strip())
        if path:
            return True, ''
        detected = [str(d.get('version') or '').strip() for d in detect_local_unity_installations() if d.get('version')]
        msg = '本机未安装 Unity %s' % uv
        if detected:
            msg += '，已检测到: %s' % '、'.join(detected)
        return False, msg
    except Exception as exc:
        return False, str(exc) or 'Unity 版本校验失败'


