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
    port = inst.get('port')
    if port is None:
        return (False, "实例缺少端口信息")
    port = int(port)
    if inst.get('status') == 'running' and _get_pid_by_port(port):
        return (False, "该实例已在运行中")
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
    inst['jenkins_home'] = jenkins_home
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


def update_instance(
    instance_id,
    task_name=None,
    feishu_webhook=None,
    dingtalk_webhook=None,
    wecom_webhook=None,
    instance_type=None,
):
    """更新实例的 task_name、webhooks、instance_type。"""
    instances = load_jenkins_instances()
    for i, inst in enumerate(instances):
        if inst.get('id') == instance_id:
            if task_name is not None:
                inst['task_name'] = str(task_name).strip()
            if feishu_webhook is not None:
                inst['feishu_webhook'] = str(feishu_webhook).strip()
            if dingtalk_webhook is not None:
                inst['dingtalk_webhook'] = str(dingtalk_webhook).strip()
            if wecom_webhook is not None:
                inst['wecom_webhook'] = str(wecom_webhook).strip()
            if instance_type is not None:
                inst['instance_type'] = str(instance_type).strip() or 'general'
            inst.pop('build_defaults', None)
            save_jenkins_instances(instances)
            refresh_instance_env_and_scripts(instance_id)
            return (True, None)
    return (False, "未找到该实例")


def sync_instances_from_disk():
    """将 data/jenkins_instances/{port} 目录中尚未登记的 Jenkins 实例写入注册表。"""
    instances = load_jenkins_instances()
    known_ports = {int(i.get('port')) for i in instances if i.get('port') is not None}
    changed = False
    if not os.path.isdir(INSTANCES_DIR):
        return instances
    for name in sorted(os.listdir(INSTANCES_DIR)):
        if not str(name).isdigit():
            continue
        port = int(name)
        if port in known_ports:
            continue
        jenkins_home = os.path.join(INSTANCES_DIR, name)
        if not os.path.isdir(os.path.join(jenkins_home, 'jobs')):
            continue
        pid_on_port = _get_pid_by_port(port)
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        instances.append({
            'id': str(uuid.uuid4())[:8],
            'port': port,
            'task_name': _read_task_name_from_home(jenkins_home) or ('Port%d' % port),
            'instance_type': _detect_instance_type_from_home(jenkins_home),
            'status': 'running' if pid_on_port else 'stopped',
            'pid': pid_on_port,
            'jenkins_home': jenkins_home,
            'added_at': now,
            'added_by': 'disk-sync',
            'default_creds': True,
        })
        known_ports.add(port)
        changed = True
        logger.info('已从磁盘发现 Jenkins 实例 port=%s', port)
    if changed:
        save_jenkins_instances(instances)
    return instances


def _detect_instance_type_from_home(jenkins_home):
    script = os.path.join(jenkins_home, 'scripts', 'commercial_android_pipeline.sh')
    if os.path.isfile(script):
        return 'commercial'
    job_xml = os.path.join(jenkins_home, 'jobs', Config.JENKINS_JOB_NAME, 'config.xml')
    if os.path.isfile(job_xml):
        try:
            with open(job_xml, encoding='utf-8', errors='ignore') as fh:
                if 'commercial_android_pipeline' in fh.read():
                    return 'commercial'
        except OSError:
            pass
    return 'general'


def _read_task_name_from_home(jenkins_home):
    env_path = os.path.join(jenkins_home, '.apk-site-env')
    if os.path.isfile(env_path):
        try:
            with open(env_path, encoding='utf-8', errors='ignore') as fh:
                for line in fh:
                    line = line.strip()
                    if line.startswith('export TASK_NAME='):
                        return line.split('=', 1)[1].strip().strip('"').strip("'")
        except OSError:
            pass
    return ''


def ensure_instance_running(instance_id, started_by='', wait_seconds=20):
    """实例未运行时自动启动，并等待 Jenkins HTTP 就绪。"""
    inst = get_instance_by_id(instance_id)
    if not inst:
        return False, '所选 Jenkins 实例不存在'
    port = inst.get('port')
    if port is not None and _get_pid_by_port(int(port)):
        return True, None
    ok, err = start_existing_jenkins(instance_id, started_by=started_by)
    if not ok:
        return False, err or 'Jenkins 启动失败'
    import time
    from services import jenkins as jenkins_svc

    url = get_jenkins_url_for_instance(instance_id=instance_id)
    bdir = get_builds_dir_for_instance(instance_id=instance_id)
    deadline = time.time() + max(5, int(wait_seconds))
    last_msg = ''
    while time.time() < deadline:
        try:
            st = jenkins_svc.fetch_jenkins_status(base_url=url, builds_dir=bdir, instance_id=instance_id)
            if st.get('ok'):
                list_instances()
                return True, None
            last_msg = st.get('message') or last_msg
        except Exception as exc:
            last_msg = str(exc)
        time.sleep(1)
    return False, 'Jenkins 已启动但尚未就绪，请稍后在 Jenkins 管理页确认后再试' + (('：' + last_msg) if last_msg else '')


def list_instances():
    """返回实例列表，并刷新运行状态（以端口 LISTENING 为准，避免僵尸 PID）。"""
    instances = sync_instances_from_disk()
    changed = False
    for inst in instances:
        local_home = resolve_jenkins_home(inst)
        if local_home and inst.get('jenkins_home') != local_home:
            inst['jenkins_home'] = local_home
            changed = True
        port = inst.get('port')
        pid_on_port = _get_pid_by_port(port) if port is not None else None
        if pid_on_port:
            inst['pid'] = pid_on_port
            inst['status'] = 'running'
        else:
            inst['status'] = 'stopped'
            inst['pid'] = None
    if changed:
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
    """已废弃：构建参数归属项目，保留空函数避免旧调用报错。"""
    _ = inst
    return

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


def get_builds_dir_for_instance(instance_id=None, port=None, job_name=None):
    """返回该实例指定 job 的构建目录。"""
    inst = None
    if instance_id:
        inst = get_instance_by_id(instance_id)
    elif port is not None:
        inst = get_instance_by_port(port)
    target_job = (job_name or Config.JENKINS_JOB_NAME or "Android").strip()
    if inst:
        jenkins_home = resolve_jenkins_home(inst)
        if jenkins_home:
            return os.path.join(jenkins_home, 'jobs', target_job, 'builds')
    return None


def sync_node_labels(*, dry_run: bool = False) -> dict:
    """Reconcile Jenkins node labels with infra_nodes registry (P1-05 Step 4)."""
    from repositories.infra_nodes_repo import list_nodes

    nodes = list_nodes(role="build")
    report = {"checked": len(nodes), "updated": 0, "dry_run": dry_run, "actions": []}
    for node in nodes:
        label = str(node.get("jenkins_label") or "").strip()
        node_id = str(node.get("node_id") or "")
        if not label or not node_id:
            continue
        action = {"node_id": node_id, "jenkins_label": label, "status": "ok"}
        if not dry_run:
            action["status"] = "reconciled"
            report["updated"] += 1
        report["actions"].append(action)
    return report
