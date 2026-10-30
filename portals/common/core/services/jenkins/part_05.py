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


def _generate_platform_job_config_xml(
    job_name: str,
    pipeline_script: str,
    assigned_node: str,
    output_base,
    build_defaults,
    instance_type='general',
):
    """Generate Jenkins job config for a platform pipeline with optional agent label."""
    content = _generate_job_config_xml(output_base, build_defaults, instance_type=instance_type)
    import re
    if instance_type == 'commercial':
        builders_block = _commercial_pipeline_builder_xml_for(pipeline_script)
        content = re.sub(
            r'<builders>.*?</builders>',
            lambda _m: builders_block,
            content,
            count=1,
            flags=re.DOTALL,
        )
    label = str(assigned_node or "").strip()
    if label:
        if re.search(r'<assignedNode>', content):
            content = re.sub(r'<assignedNode>.*?</assignedNode>', f'<assignedNode>{label}</assignedNode>', content, count=1)
        else:
            content = content.replace('<canRoam>true</canRoam>', f'<canRoam>false</canRoam>\n  <assignedNode>{label}</assignedNode>')
    content = content.replace('<concurrentBuild>false</concurrentBuild>', '<concurrentBuild>true</concurrentBuild>', 1)
    return content


def _platform_job_definitions():
    from services.build.build_grid import BUILD_ROLES, BUILD_ROLE_ANDROID, BUILD_ROLE_IOS, BUILD_ROLE_WXMINIGAME

    rows = []
    for role_key, job_name in (
        (BUILD_ROLE_ANDROID, "Android"),
        (BUILD_ROLE_IOS, "iOS"),
        (BUILD_ROLE_WXMINIGAME, "WxMinigame"),
    ):
        meta = BUILD_ROLES.get(role_key) or {}
        rows.append((job_name, str(meta.get("pipeline_script") or ""), str(meta.get("label") or "")))
    return rows


def sync_all_platform_jobs(instance_id, build_defaults_override=None, project_id=''):
    """Sync Android/iOS/WxMinigame Jenkins jobs for distributed build grid."""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False
    jenkins_home = resolve_jenkins_home(inst)
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return False
    build_defaults = dict(_resolve_build_defaults_for_project(project_id, inst))
    if isinstance(build_defaults_override, dict):
        build_defaults.update(build_defaults_override)
    output_base = get_instance_output_base(inst, project_id=project_id)
    instance_type = inst.get('instance_type', 'general')
    try:
        for job_name, pipeline_script, assigned_node in _platform_job_definitions():
            job_dir = os.path.join(jenkins_home, 'jobs', job_name)
            os.makedirs(job_dir, exist_ok=True)
            content = _generate_platform_job_config_xml(
                job_name,
                pipeline_script,
                assigned_node,
                output_base,
                build_defaults,
                instance_type=instance_type,
            )
            with open(os.path.join(job_dir, 'config.xml'), 'w', encoding='utf-8') as f:
                f.write(content)
        _write_unity_paths_json(jenkins_home, build_defaults)
        logger.info("已同步平台 Jenkins 任务: %s", jenkins_home)
        return True
    except Exception as exc:
        logger.warning("同步平台 Jenkins 任务失败: %s", exc)
        return False


def sync_instance_job_config(instance_id, build_defaults_override=None, project_id=''):
    """按项目 build_config（及可选 override）重新生成 Android job config.xml 与 unity_paths.json。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False
    jenkins_home = resolve_jenkins_home(inst)
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return False
    job_dir = os.path.join(jenkins_home, 'jobs', 'Android')
    build_defaults = dict(_resolve_build_defaults_for_project(project_id, inst))
    if isinstance(build_defaults_override, dict):
        build_defaults.update(build_defaults_override)
    output_base = get_instance_output_base(inst, project_id=project_id)
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


def prepare_instance_job_for_plan(instance_id, plan: dict, project_id: str = '') -> tuple[bool, str]:
    """触发商业构建前：把 plan 中的 GIT_BRANCH / UNITY_VERSION 写入 Job 参数定义并 reload。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False, 'Jenkins 实例不存在'
    ok_uv, uv_err = _validate_plan_unity_installation(plan or {})
    if not ok_uv:
        return False, uv_err
    base_bd = _resolve_build_defaults_for_project(project_id, inst)
    bd = _merge_build_defaults_for_plan(base_bd, plan or {})
    if not sync_instance_job_config(instance_id, build_defaults_override=bd, project_id=project_id):
        return False, '同步 Jenkins Job 参数失败'
    ok_env, env_err = apply_project_build_env(instance_id, project_id, bd)
    if not ok_env:
        return False, env_err or '写入项目构建环境失败'
    if not reload_jenkins_job(instance_id):
        logger.warning(
            'Jenkins reload 未成功（常见 403）；若触发仍报 HTTP 500/Illegal choice，'
            '请在 Jenkins 管理中重启该实例一次以加载新 Job 参数。'
        )
    return True, ''


def _resolve_build_defaults_for_project(project_id: str, inst: dict | None) -> dict:
    """从项目 build_config 读取构建默认值。"""
    _ = inst
    try:
        from services.admin.project_build_config_service import get_project_build_config

        return get_project_build_config(project_id) if project_id else {}
    except Exception:
        return {}


def apply_project_build_env(instance_id, project_id='', build_defaults_override=None):
    """按项目构建配置刷新实例 .apk-site-env（Git / Unity 路径等）。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False, 'Jenkins 实例不存在'
    jenkins_home = resolve_jenkins_home(inst)
    if not jenkins_home or not os.path.isdir(jenkins_home):
        return False, 'Jenkins 实例目录不可用'
    bd = dict(_resolve_build_defaults_for_project(project_id, inst))
    if isinstance(build_defaults_override, dict):
        bd.update(build_defaults_override)
    output_base = get_instance_output_base(inst, project_id=project_id)
    out_dir = (bd.get('output_base_dir') or '').strip()
    if out_dir:
        output_base = out_dir
    _write_instance_env_and_scripts(
        jenkins_home,
        inst.get('port'),
        inst.get('task_name') or '',
        output_base,
        inst.get('feishu_webhook') or '',
        inst.get('dingtalk_webhook') or '',
        inst.get('wecom_webhook') or '',
        bd,
    )
    return True, ''


def prepare_instance_for_project_build(instance_id, project_id='', git_branch='', plan=None):
    """通用/商业构建触发前：同步 Job 参数并从项目注入 Git 环境。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False, 'Jenkins 实例不存在'
    try:
        from services.admin.project_build_config_service import merge_git_branch_into_defaults

        bd = _resolve_build_defaults_for_project(project_id, inst)
        if git_branch:
            bd = merge_git_branch_into_defaults(bd, git_branch)
        if isinstance(plan, dict) and plan:
            bd = _merge_build_defaults_for_plan(bd, plan)
        if not sync_all_platform_jobs(instance_id, build_defaults_override=bd, project_id=project_id):
            return False, '同步 Jenkins Job 参数失败'
        ok_env, env_err = apply_project_build_env(instance_id, project_id, bd)
        if not ok_env:
            return False, env_err or '写入项目构建环境失败'
        for job_name, _, _ in _platform_job_definitions():
            reload_jenkins_job(instance_id, job_name=job_name)
        return True, ''
    except Exception as exc:
        logger.warning('prepare_instance_for_project_build 失败: %s', exc)
        return False, str(exc) or '准备 Jenkins 构建环境失败'


def start_jenkins(
    port,
    started_by='',
    task_name='',
    feishu_webhook='',
    dingtalk_webhook='',
    wecom_webhook='',
    instance_type='general',
):
    """启动一个 Jenkins 实例。支持飞书 / 钉钉 / 企微多渠道通知。"""
    ok, msg = check_port(port)
    if not ok:
        return (False, None, msg)
    port = int(port)
    task_name = (task_name or '').strip()
    feishu_webhook = (feishu_webhook or '').strip()
    dingtalk_webhook = (dingtalk_webhook or '').strip()
    wecom_webhook = (wecom_webhook or '').strip()
    war = get_jenkins_war_path()
    if not war:
        return (False, None, "未找到 jenkins.war。请在 .env 中设置 JENKINS_WAR_PATH 或将 war 放到 data/jenkins_instances/jenkins.war")
    jenkins_home = os.path.join(INSTANCES_DIR, str(port))
    os.makedirs(jenkins_home, exist_ok=True)
    output_base = get_instance_output_base({'task_name': task_name, 'port': port})
    # 注入固定管理员脚本并跳过安装向导
    _write_jenkins_init_admin_script(jenkins_home, Config.JENKINS_DEFAULT_USER, Config.JENKINS_DEFAULT_PASSWORD)
    # 复制 Android 任务（Unity 版本下拉来自全局版本库）
    _copy_android_job_to_jenkins_home(jenkins_home, port=port, task_name=task_name, build_defaults=None, instance_type=instance_type)
    # 写入 .apk-site-env 与通知 webhook，并复制通知脚本
    _write_instance_env_and_scripts(
        jenkins_home,
        port,
        task_name,
        output_base,
        feishu_webhook,
        dingtalk_webhook,
        wecom_webhook,
        None,
    )
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
        'wecom_webhook': wecom_webhook,
        'instance_type': instance_type,
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


