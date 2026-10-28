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


