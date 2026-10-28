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
    candidates = []
    if Config.JENKINS_WAR_PATH:
        candidates.append(Config.JENKINS_WAR_PATH)
    candidates.append(os.path.join(JENKINS_CLONE_DIR, 'jenkins.war'))
    candidates.append(os.path.join(INSTANCES_DIR, 'jenkins.war'))
    for path in candidates:
        if path and os.path.isfile(path):
            return path
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
    """Write init.groovy.d admin script only when password is configured. Plan P0-01."""
    pwd = str(password or '').strip()
    if not pwd:
        logger.warning(
            "跳过 Jenkins 初始管理员脚本：未配置 JENKINS_DEFAULT_PASSWORD，请通过 env 或 jenkins_credentials.json 设置"
        )
        return
    init_d = os.path.join(jenkins_home, 'init.groovy.d')
    os.makedirs(init_d, exist_ok=True)
    u = (user or 'admin').replace('\\', '\\\\').replace('"', '\\"')
    p = pwd.replace('\\', '\\\\').replace('"', '\\"')
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


def _commercial_pipeline_builder_xml_for(pipeline_script: str):
    """Commercial builder block referencing a specific pipeline script under JENKINS_HOME/scripts/."""
    script = str(pipeline_script or "commercial_android_pipeline.sh").strip()
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
            'if not exist "%%JENKINS_HOME%%\\scripts\\%s" (\r\n'
            '  echo ERROR: missing pipeline script %s\r\n'
            '  exit /b 1\r\n'
            ')\r\n'
            '"%%BASH%%" "%%JENKINS_HOME%%\\scripts\\%s"\r\n'
            'exit /b %%ERRORLEVEL%%\r\n'
        ) % (bash_exe.replace('%', '%%'), script, script, script)
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
        'PIPELINE="${JENKINS_HOME}/scripts/%s"\n'
        'if [ ! -f "$PIPELINE" ]; then\n'
        '  echo "ERROR: missing $PIPELINE"\n'
        '  exit 1\n'
        'fi\n'
        'exec bash "$PIPELINE"\n'
    ) % script
    return (
        '  <builders>\n'
        '    <hudson.tasks.Shell>\n'
        '      <command>%s</command>\n'
        '      <configuredLocalRules/>\n'
        '    </hudson.tasks.Shell>\n'
        '  </builders>' % cmd
    )


