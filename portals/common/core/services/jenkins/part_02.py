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


