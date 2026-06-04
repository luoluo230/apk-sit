#!/bin/bash
set -e

# ===== 编码与日志环境（Windows Git Bash + macOS 通用）=====
export LANG="${LANG:-C.UTF-8}"
export LC_ALL="${LC_ALL:-C.UTF-8}"
export PYTHONUTF8=1
export PYTHONIOENCODING="${PYTHONIOENCODING:-utf-8}"
if command -v chcp.com >/dev/null 2>&1; then
  # Windows 控制台切 UTF-8，避免 Jenkins 控制台中文乱码
  chcp.com 65001 >/dev/null 2>&1 || true
fi

_log_stage() {
  local step="$1"
  local title="$2"
  local detail="$3"
  echo ""
  echo "=============================="
  echo "[阶段 ${step}] ${title}"
  echo "说明: ${detail}"
  echo "时间: $(date '+%Y-%m-%d %H:%M:%S')"
  echo "=============================="
}

echo "======================================="
echo "  GameKu Android 构建 (Jenkins)"
echo "======================================="
echo ""
echo "构建参数:"
echo "  Unity 版本: $UNITY_VERSION"
echo "  版本号: $VERSION_NAME"
echo "  版本代码: $VERSION_CODE"
echo "  应用名称: $APP_NAME"
echo "  Git 分支: ${GIT_BRANCH:-默认}"
_log_stage "0" "环境准备" "输出构建参数、加载实例环境变量、准备 Git/Unity 执行上下文。"

# 若配置了 GIT_URL 与 Git 工作目录，先拉取/更新代码（使用实例 .apk-site-env 中的 GIT_URL、GIT_SSH_KEY_PATH、GIT_WORKSPACE）
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-env" ] && . "${JENKINS_HOME}/.apk-site-env"
if [ -n "$GIT_URL" ] && [ -n "$GIT_WORKSPACE" ]; then
  echo "步骤: Git 拉取/更新 ($GIT_WORKSPACE)"
  if [ -n "$GIT_SSH_KEY_PATH" ] && [ -f "$GIT_SSH_KEY_PATH" ]; then
    export GIT_SSH_COMMAND="ssh -i $GIT_SSH_KEY_PATH -o StrictHostKeyChecking=no"
  fi
  BRANCH="${GIT_BRANCH:-main}"
  [ "${BRANCH#origin/}" != "$BRANCH" ] && LOCAL_BRANCH="${BRANCH#origin/}" || LOCAL_BRANCH="$BRANCH"
  set +e
  if [ -d "$GIT_WORKSPACE/.git" ]; then
    (cd "$GIT_WORKSPACE" && git fetch origin 2>&1 || true && \
     if git rev-parse -q --verify "origin/$LOCAL_BRANCH" >/dev/null 2>&1; then \
       git checkout -B "$LOCAL_BRANCH" "origin/$LOCAL_BRANCH"; \
     else \
       echo "远程无 origin/$LOCAL_BRANCH，尝试使用本地分支"; \
       git checkout "$LOCAL_BRANCH" 2>/dev/null || git checkout "$BRANCH" 2>/dev/null || true; \
     fi)
  else
    mkdir -p "$(dirname "$GIT_WORKSPACE")"
    git clone -b "$LOCAL_BRANCH" "$GIT_URL" "$GIT_WORKSPACE" || true
  fi
  set -e
  echo "Git 拉取完成"
fi

_resolve_apk_build_script() {
  local candidates=()
  [ -n "${APK_BUILD_SCRIPT:-}" ] && candidates+=("$APK_BUILD_SCRIPT")
  [ -n "${JENKINS_HOME:-}" ] && candidates+=("${JENKINS_HOME}/scripts/build_gameku_android.sh")
  candidates+=("$HOME/build_gameku_android.sh" "/Users/$(whoami 2>/dev/null || echo Administrator)/build_gameku_android.sh")
  local c
  for c in "${candidates[@]}"; do
    [ -n "$c" ] && [ -f "$c" ] && { echo "$c"; return 0; }
  done
  return 1
}

# 可选：先执行传统 APK 构建脚本（商业热更默认关闭；仅 APK_BUILD_ENABLED 或显式 RUN_BASE_APK_BUILD_FIRST=true 时执行）
if [ "${RUN_BASE_APK_BUILD_FIRST:-false}" = "true" ]; then
  _log_stage "0A" "基础 APK 预构建" "启用 RUN_BASE_APK_BUILD_FIRST=true，先执行传统 APK 预构建脚本。"
  APK_SCRIPT="$(_resolve_apk_build_script || true)"
  if [ -z "$APK_SCRIPT" ]; then
    echo "WARN: 未找到 build_gameku_android.sh，跳过基础 APK 预构建（请配置 APK_BUILD_SCRIPT 或 JENKINS_HOME/scripts/）"
  else
    bash "$APK_SCRIPT"
  fi
else
  echo "跳过基础 APK 预构建（RUN_BASE_APK_BUILD_FIRST=false）"
fi

echo ""
echo "======= 可插拔版本构建流水线 ======="
[ -n "$JENKINS_HOME" ] && [ -f "${JENKINS_HOME}/.apk-site-env" ] && . "${JENKINS_HOME}/.apk-site-env"

_resolve_unity_exe() {
  local ver="${UNITY_VERSION:-6000.3.8f1}"
  local map_file="${UNITY_PATH_MAP_FILE:-${JENKINS_HOME}/unity_paths.json}"
  local resolved=""
  local py_cmd=""
  if command -v python3 >/dev/null 2>&1; then py_cmd="python3"
  elif command -v python >/dev/null 2>&1; then py_cmd="python"
  elif command -v py >/dev/null 2>&1; then py_cmd="py -3"
  fi
  if [ -f "$map_file" ] && [ -n "$py_cmd" ]; then
    resolved=$($py_cmd -c "import json,os; m=json.load(open(os.environ['UNITY_PATH_MAP_FILE'],encoding='utf-8')); print((m.get(os.environ.get('UNITY_VERSION','')) or '').strip())" 2>/dev/null || echo "")
  fi
  if [ -n "$resolved" ] && [ -d "$resolved" ] && [ -f "$resolved/Contents/MacOS/Unity" ]; then
    resolved="$resolved/Contents/MacOS/Unity"
  fi
  if [ -z "$resolved" ] || [ ! -f "$resolved" ]; then
  for CAND in \
    "/c/Program Files/Unity/Hub/Editor/${ver}/Editor/Unity.exe" \
    "/c/Program Files (x86)/Unity/Hub/Editor/${ver}/Editor/Unity.exe" \
    "/Applications/Unity/Hub/Editor/${ver}/Unity.app/Contents/MacOS/Unity" \
    "$HOME/Applications/Unity/Hub/Editor/${ver}/Unity.app/Contents/MacOS/Unity"
  do
    if [ -f "$CAND" ]; then
      resolved="$CAND"
      break
    fi
  done
  fi
  if [ -z "$resolved" ] || [ ! -f "$resolved" ]; then
    if [ -n "${UNITY_HUB:-}" ] && [ "${UNITY_HUB}" != "/" ]; then
      local hub_cand="${UNITY_HUB%/}/Editor/${ver}/Unity.app/Contents/MacOS/Unity"
      if [ -f "$hub_cand" ]; then
        resolved="$hub_cand"
      fi
      if [ -z "$resolved" ] || [ ! -f "$resolved" ]; then
        hub_cand="${UNITY_HUB%/}/Editor/${ver}/Editor/Unity.exe"
        if [ -f "$hub_cand" ]; then
          resolved="$hub_cand"
        fi
      fi
    fi
  fi
  if [ -n "$resolved" ] && [ -f "$resolved" ]; then
    echo "$resolved"
  fi
}
UNITY_PATH="$(_resolve_unity_exe)"
echo "Unity 可执行文件: ${UNITY_PATH:-（未解析）}"

_cache_unity_services_cdn() {
  local url="https://public-cdn.cloud.unity3d.com/config/production"
  local dest="${JENKINS_HOME:-}/unity-services-config-production.json"
  if [ -z "$JENKINS_HOME" ]; then
    dest="${TMPDIR:-/tmp}/unity-services-config-production.json"
  fi
  echo "预拉取 Unity Services CDN 配置 (最长 90s)..."
  if [ ! -f "$dest" ]; then
    curl -fsS --connect-timeout 10 --max-time 90 "$url" -o "$dest" 2>/dev/null || true
  fi
  if [ ! -f "$dest" ]; then
    echo "⚠ CDN 配置拉取失败"
    return 1
  fi
  local bytes
  bytes=$(wc -c "$dest" | awk '{print $1}')
  echo "CDN 配置已缓存 (${bytes} bytes) @ $dest"
  local unity_cfg_dir="${HOME}/Library/Application Support/Unity/config"
  mkdir -p "$unity_cfg_dir"
  cp -f "$dest" "${unity_cfg_dir}/services-config.json"
  echo "Unity offline config: ${unity_cfg_dir}/services-config.json"
}

_prefetch_unity_cdn() {
  _cache_unity_services_cdn
}

_warmup_unity() {
  local PROJECT_PATH="${UNITY_PROJECT_PATH:-}"
  [ -z "$PROJECT_PATH" ] || [ ! -d "$PROJECT_PATH/Assets" ] && return 0
  echo "=== Unity 脚本预热（编译） ==="
  local saved_log="$UNITY_LOG"
  local saved_keep="$UNITY_LOG_KEEP"
  local saved_req="$UNITY_REQUIRE_OSS_DONE"
  unset UNITY_LOG UNITY_LOG_KEEP UNITY_REQUIRE_OSS_DONE
  _prefetch_unity_cdn
  _run_unity ReleaseToolsWarmup.EnsureCompiled || echo "⚠ 预热非零退出（可继续）"
  [ -n "$saved_log" ] && export UNITY_LOG="$saved_log"
  [ -n "$saved_keep" ] && export UNITY_LOG_KEEP="$saved_keep"
  [ -n "$saved_req" ] && export UNITY_REQUIRE_OSS_DONE="$saved_req"
}

_map_config_cli_env() {
  local e="${1:-Development}"
  case "$(echo "$e" | tr '[:upper:]' '[:lower:]')" in
    test|testing) echo "Test" ;;
    stage|staging) echo "Stage" ;;
    prod|production) echo "Prod" ;;
    *) echo "Dev" ;;
  esac
}

_resolve_config_remote_prefix() {
  local raw="${1:-}"
  if [ -n "$raw" ] && [ "${raw#*/}" = "$raw" ]; then
    echo "$raw"
    return 0
  fi
  echo "MyGame1"
}

_verify_step1_log() {
  local log_file="$1"
  local min_files="${STEP1_MIN_OSS_DONE:-11}"
  if [ ! -f "$log_file" ]; then
    echo "⚠ Step1 日志不存在"
    return 1
  fi
  if ! grep -q '\[ConfigRemotePublishCli\] Success' "$log_file" 2>/dev/null; then
    echo "⚠ Step1 未出现 [ConfigRemotePublishCli] Success"
    return 1
  fi
  if ! grep -q '\[ConfigPublish\] Upload finished' "$log_file" 2>/dev/null; then
    echo "⚠ Step1 未出现 [ConfigPublish] Upload finished"
    return 1
  fi
  local published upload_starts
  published=$(grep -Eo 'files=[0-9]+' "$log_file" 2>/dev/null | tail -1 | cut -d= -f2)
  published="${published:-0}"
  upload_starts=$(grep -c '\[ConfigPublish\] Upload start' "$log_file" 2>/dev/null || echo 0)
  if [ "$upload_starts" -lt 1 ]; then
    echo "⚠ Step1 未开始 OSS 上传"
    return 1
  fi
  if [ "$published" -lt "$min_files" ] 2>/dev/null; then
    echo "⚠ Step1 发布文件数不足: ${published}/${min_files}"
    return 1
  fi
  echo "✅ Step1 校验通过: ConfigRemotePublishCli Success, published files=${published}"
  return 0
}

_run_unity() {
  local METHOD="$1"; shift
  if [ ! -f "$UNITY_PATH" ]; then echo "⚠ Unity 路径无效: $UNITY_PATH"; return 1; fi
  local PROJECT_PATH="${UNITY_PROJECT_PATH:-}"
  if [ -z "$PROJECT_PATH" ] || [ ! -d "$PROJECT_PATH/Assets" ]; then
    local SEARCH_ROOTS=()
    [ -n "$GIT_WORKSPACE" ] && SEARCH_ROOTS+=("$GIT_WORKSPACE")
    [ -n "$JENKINS_CLONE" ] && SEARCH_ROOTS+=("$(dirname "$JENKINS_CLONE")" "$(dirname "$(dirname "$JENKINS_CLONE")")")
    [ -n "$OUTPUT_BASE_DIR" ] && SEARCH_ROOTS+=("$(dirname "$OUTPUT_BASE_DIR")")
    local ROOT
    for ROOT in "${SEARCH_ROOTS[@]}"; do
      [ -d "$ROOT" ] || continue
      local CANDIDATE
      CANDIDATE=$(find "$ROOT" -maxdepth 4 -type d -name Assets 2>/dev/null | while read -r A; do
        P="$(dirname "$A")"
        if [ -d "$P/Assets/Editor" ] && [ -d "$P/ProjectSettings" ]; then
          echo "$P"
          break
        fi
      done)
      if [ -n "$CANDIDATE" ]; then
        PROJECT_PATH="$CANDIDATE"
        break
      fi
    done
  fi
  if [ -z "$PROJECT_PATH" ] || [ ! -d "$PROJECT_PATH/Assets/Editor" ]; then
    echo "⚠ Unity 项目目录未配置或缺少 Assets/Editor（可传 UNITY_PROJECT_PATH，或配置 GIT_WORKSPACE）"
    return 1
  fi
  local UNITY_TIMEOUT_SEC="${UNITY_CLI_TIMEOUT_SEC:-7200}"
  local ARGS="-batchmode -nographics -disableAssemblyUpdater -quitTimeout ${UNITY_TIMEOUT_SEC} -projectPath \"$PROJECT_PATH\" -executeMethod $METHOD $*"
  echo "Unity Project: $PROJECT_PATH"
  echo "→ 执行: $UNITY_PATH $ARGS"
  _cache_unity_services_cdn
  export UNITY_EDITOR_DISABLE_EXTERNAL_UPDATES=1
  set +e
  UNITY_LOG="${UNITY_LOG:-$(mktemp)}"
  # shellcheck disable=SC2086
  eval "\"$UNITY_PATH\" $ARGS" 2>&1 | tee "$UNITY_LOG"
  local UNITY_EC=${PIPESTATUS[0]}
  set -e
  if [ $UNITY_EC -ne 0 ]; then
    local oss_done=0
    oss_done=$(grep -c 'done remote=' "$UNITY_LOG" 2>/dev/null || echo 0)
    if [ -n "${UNITY_REQUIRE_OSS_DONE:-}" ]; then
      if [ "$oss_done" -ge "${UNITY_REQUIRE_OSS_DONE}" ] 2>/dev/null; then
        echo "⚠ Unity 退出码 $UNITY_EC，但 OSS 已完成 ${oss_done}/${UNITY_REQUIRE_OSS_DONE}，继续"
        [ -z "${UNITY_LOG_KEEP:-}" ] && rm -f "$UNITY_LOG"
        return 0
      fi
    elif grep -qE '\[ReleaseUpload\]\[AliyunOSS\].*done remote=|\[M09-08B\]\[CLI\] ExitCode=0 Success=True|\[ApkReleaseUploadCli\] APK upload completed' "$UNITY_LOG" 2>/dev/null; then
      echo "⚠ Unity 退出码 $UNITY_EC，但检测到 CLI/OSS 成功日志，继续流水线"
      [ -z "${UNITY_LOG_KEEP:-}" ] && rm -f "$UNITY_LOG"
      return 0
    fi
    echo "⚠ Unity 退出码: $UNITY_EC"
    [ -z "${UNITY_LOG_KEEP:-}" ] && rm -f "$UNITY_LOG"
    return $UNITY_EC
  fi
  [ -z "${UNITY_LOG_KEEP:-}" ] && rm -f "$UNITY_LOG"
}


_sanitize_release_targets() {
  local raw="${1:-code,resource}"
  local lowered
  lowered="$(echo "$raw" | tr '[:upper:]' '[:lower:]')"
  if echo "$lowered" | grep -qE '(^|,)all(,|$)'; then
    echo "code,resource"
    return 0
  fi
  local out=""
  local part
  for part in $(echo "$lowered" | tr ',' ' '); do
    case "$part" in
      code|resource)
        if ! echo "$out" | grep -qE "(^|,)${part}(,|$)"; then
          [ -n "$out" ] && out="${out},"
          out="${out}${part}"
        fi
        ;;
      config)
        echo "⚠ RELEASE_TARGETS 含 config，已剥离（配置仅 Step1 ConfigRemotePublish）" >&2
        ;;
    esac
  done
  [ -n "$out" ] && echo "$out" || echo "code,resource"
}

_run_publish_only_mode() {
  local mode
  mode="$(echo "${RELEASE_MODE:-${COMMERCIAL_RELEASE_MODE:-}}" | tr '[:upper:]' '[:lower:]')"
  case "$mode" in
    activate|rollback) ;;
    *) return 1 ;;
  esac
  echo "=== Step 4: 版本${mode}（跳过 Step1-3 构建） ==="
  HR_ARGS="-releaseVersion \"${RELEASE_VERSION:-0.0.1}\""
  HR_ARGS="$HR_ARGS -releaseEnvironment \"${RELEASE_ENVIRONMENT:-Development}\""
  HR_ARGS="$HR_ARGS -releaseChannel \"${RELEASE_CHANNEL:-common}\""
  HR_ARGS="$HR_ARGS -releasePlatform \"${RELEASE_PLATFORM:-Android}\""
  HR_ARGS="$HR_ARGS -commercialReleaseMode \"${mode}\""
  [ -n "${RELEASE_PLAN_FILE}" ] && [ -f "${RELEASE_PLAN_FILE}" ] && HR_ARGS="$HR_ARGS -releasePlanFile \"${RELEASE_PLAN_FILE}\""
  [ "$mode" = "activate" ] && HR_ARGS="$HR_ARGS -releaseActivate \"true\""
  [ -n "${RELEASE_ROLLBACK_TARGET}" ] && HR_ARGS="$HR_ARGS -releaseRollbackTarget \"${RELEASE_ROLLBACK_TARGET}\""
  _warmup_unity || echo "⚠ 预热非零退出（可继续）"
  sleep 3
  _run_unity CommercialReleaseCli.ExecuteFromCommandLine $HR_ARGS || exit $?
  echo "Step 4 (${mode}) 完成"
  return 0
}

RELEASE_TARGETS="$(_sanitize_release_targets "${RELEASE_TARGETS:-code,resource}")"
export RELEASE_TARGETS

if _run_publish_only_mode; then
  echo "商业流水线完成（仅 ${RELEASE_MODE:-${COMMERCIAL_RELEASE_MODE}}）"
  exit 0
fi

# Step 1: 配置导出发布（ConfigRemotePublish：Excel 导表 → manifest → OSS）
if [ "${CONFIG_EXPORT_ENABLED:-false}" = "true" ]; then
  _log_stage "1" "配置导出发布" "执行 ConfigRemotePublishCli：导表、生成配置补丁清单、上传 OSS。"
  echo "=== Step 1: 配置导出发布 (ConfigRemotePublish) ==="
  echo "上传: ConfigContent Excel 导表 + CloudUpload/OSS"
  _CFG_ENV="$(_map_config_cli_env "${CONFIG_ENVIRONMENT:-${RELEASE_ENVIRONMENT:-Development}}")"
  _CFG_PLATFORM="${CONFIG_PLATFORM:-${RELEASE_PLATFORM:-Android}}"
  _CFG_CHANNEL="${RELEASE_CHANNEL:-${CHANNEL:-wechat}}"
  _CFG_VERSION="${CONFIG_CLIENT_VERSION:-${RELEASE_VERSION:-1.0.0}}"
  _CFG_VERSION_CODE="${VERSION_CODE:-1}"
  _CFG_PREFIX="$(_resolve_config_remote_prefix "${CONFIG_REMOTE_PREFIX:-}")"
  _CFG_SCHEMA="${CONFIG_SCHEMA_ASSET:-Assets/Editor/ConfigContentTool/ConfigContentSchema.asset}"
  CFG_ARGS="-configSchema \"${_CFG_SCHEMA}\""
  CFG_ARGS="$CFG_ARGS -configEnvironment \"${_CFG_ENV}\""
  CFG_ARGS="$CFG_ARGS -configPlatform \"${_CFG_PLATFORM}\""
  CFG_ARGS="$CFG_ARGS -configChannel \"${_CFG_CHANNEL}\""
  CFG_ARGS="$CFG_ARGS -configClientVersion \"${_CFG_VERSION}\""
  CFG_ARGS="$CFG_ARGS -configVersionCode \"${_CFG_VERSION_CODE}\""
  CFG_ARGS="$CFG_ARGS -configRemotePrefix \"${_CFG_PREFIX}\""
  CFG_ARGS="$CFG_ARGS -configIncludeCode \"${CONFIG_INCLUDE_CODE:-false}\""
  CFG_ARGS="$CFG_ARGS -configTimeoutSeconds \"${CONFIG_PUBLISH_TIMEOUT_SEC:-600}\""
  CFG_ARGS="$CFG_ARGS -resultOutputPath \"Library/ConfigPublish/cli-result.json\""
  echo "Step1 参数: env=${_CFG_ENV} channel=${_CFG_CHANNEL} platform=${_CFG_PLATFORM} version=${_CFG_VERSION} versionCode=${_CFG_VERSION_CODE} prefix=${_CFG_PREFIX}"
  UNITY_LOG="$(mktemp)"
  export UNITY_LOG
  export UNITY_LOG_KEEP=1
  unset UNITY_REQUIRE_OSS_DONE
  echo "Unity Editor 程序集预热编译..."
  _warmup_unity || echo "⚠ 预热非零退出（可继续 Step1）"
  sleep 3
  if ! _run_unity "MAClient.ConfigContentTool.ConfigRemotePublishCli.ExecuteFromCommandLine" $CFG_ARGS; then
    _verify_step1_log "$UNITY_LOG" || { echo "FAIL: Step1 ConfigRemotePublish 退出"; exit 1; }
  fi
  _verify_step1_log "$UNITY_LOG" || exit 1
  rm -f "$UNITY_LOG"
  unset UNITY_LOG UNITY_LOG_KEEP
  echo "Step 1 完成"
else
  echo "Step 1 (配置导出) 已跳过"
fi

# Step 2: 资源打包（调用 M09-08B 资源流水线 CLI）
if [ "${RESOURCE_BUILD_ENABLED:-false}" = "true" ]; then
  _log_stage "2" "资源打包" "执行 ResourcePipelineCli：构建 Addressables 与资源产物目录。"
  echo "=== Step 2: 资源打包 ==="
  if [ "${RESOURCE_CLEAN_VERSION:-true}" = "true" ]; then
    VER_ROOT="${UNITY_PROJECT_PATH:-${GIT_WORKSPACE:-}}"
    if [ -n "$VER_ROOT" ]; then
      VER_DIR="$VER_ROOT/Builds/${RELEASE_ENVIRONMENT:-Development}/${RELEASE_CHANNEL:-common}/${RELEASE_PLATFORM:-Android}/Version_${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}"
      if [ -d "$VER_DIR" ]; then
        rm -rf "$VER_DIR"
        echo "已清理版本目录: $VER_DIR"
      fi
    fi
  fi
  RP_ARGS="-m09bMode \"build\""
  RP_ARGS="$RP_ARGS -m09bVersion \"${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}\""
  RP_ARGS="$RP_ARGS -m09bEnvironment \"${RELEASE_ENVIRONMENT:-Development}\""
  RP_ARGS="$RP_ARGS -m09bChannel \"${RELEASE_CHANNEL:-common}\""
  RP_ARGS="$RP_ARGS -m09bPlatform \"${RELEASE_PLATFORM:-Android}\""
  [ -n "${RESOURCE_PROVIDER}" ] && RP_ARGS="$RP_ARGS -m09bProvider \"${RESOURCE_PROVIDER}\""
  if [ -n "${RESOURCE_SCENARIO}" ] && [[ "${RESOURCE_SCENARIO}" == *"/"* || "${RESOURCE_SCENARIO}" == *.json ]]; then
    RP_ARGS="$RP_ARGS -m09bScenario \"${RESOURCE_SCENARIO}\""
  fi
  RP_ARGS="$RP_ARGS -m09bVersionCode \"${VERSION_CODE}\""
  RP_ARGS="$RP_ARGS -m09bCleanVersion \"${RESOURCE_CLEAN_VERSION:-true}\""
  RP_ARGS="$RP_ARGS -m09bBridgeStrict \"${RESOURCE_BRIDGE_STRICT:-false}\" -m09bAcceptanceStrict \"${RESOURCE_ACCEPTANCE_STRICT:-false}\""
  echo "Unity Editor 程序集预热（Step2）..."
  _warmup_unity || echo "⚠ Step2 预热非零退出（可继续）"
  sleep 3
  _step2_attempt=1
  while [ "$_step2_attempt" -le 2 ]; do
    if _run_unity ResourcePipelineCli.ExecuteFromCommandLine $RP_ARGS; then
      break
    fi
    _step2_ec=$?
    if [ "$_step2_attempt" -lt 2 ] && [ "$_step2_ec" -eq 138 ]; then
      echo "⚠ Step2 Unity Bus error (${_step2_ec})，30s 后重试 (${_step2_attempt}/2)..."
      sleep 30
      _warmup_unity || true
      sleep 3
      _step2_attempt=$((_step2_attempt + 1))
      continue
    fi
    exit "$_step2_ec"
  done
  echo "Step 2 完成"
else
  echo "Step 2 (资源打包) 已跳过"
fi

# Step 3: 代码+资源热更发布（构建+压缩+签名+上传阿里云，配置/代码/资源包均走 CommercialReleaseCli）
if [ "${HOT_RELEASE_ENABLED:-false}" = "true" ]; then
  _log_stage "3" "代码与热更发布" "执行 CommercialReleaseCli：构建代码包、生成 patch/签名、按目标上传 OSS。"
  echo "=== Step 3: 代码+资源热更发布 ==="
  echo "上传: Unity 项目 Assets/Editor/Configs/OSSConfig.json (aliyun-oss)"
  HR_ARGS="-releaseVersion \"${RELEASE_VERSION:-0.0.1}\""
  HR_ARGS="$HR_ARGS -releaseEnvironment \"${RELEASE_ENVIRONMENT:-Development}\""
  HR_ARGS="$HR_ARGS -releaseChannel \"${RELEASE_CHANNEL:-common}\""
  HR_ARGS="$HR_ARGS -releasePlatform \"${RELEASE_PLATFORM:-Android}\""
  HR_ARGS="$HR_ARGS -releaseTargets \"${RELEASE_TARGETS:-code,resource}\""
  HR_ARGS="$HR_ARGS -releaseHotLabels \"${RELEASE_HOT_LABELS:-hotupdate,aotmeta}\""
  HR_ARGS="$HR_ARGS -releaseUpload \"${RELEASE_UPLOAD:-true}\""
  HR_ARGS="$HR_ARGS -versionCode \"${VERSION_CODE}\""
  _step3_upload_mode="${RELEASE_UPLOAD_MODE:-incremental}"
  _vc_parent="${UNITY_PROJECT_PATH:-${GIT_WORKSPACE:-}}/Builds/${RELEASE_ENVIRONMENT:-Development}/${RELEASE_CHANNEL:-common}/${RELEASE_PLATFORM:-Android}/Version_${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}"
  if [ "${_step3_upload_mode}" = "incremental" ] && [ -d "${_vc_parent}" ]; then
    _prev_vc_count=$(find "${_vc_parent}" -maxdepth 1 -mindepth 1 -type d -name '[0-9]*' ! -name "${VERSION_CODE}" 2>/dev/null | wc -l | tr -d ' ')
    if [ "${_prev_vc_count:-0}" = "0" ]; then
      _step3_upload_mode="full"
      echo "无上一 VersionCode 目录，Step3 切换为 full 上传（含 addressable bundle）"
    fi
  fi
  HR_ARGS="$HR_ARGS -releaseUploadMode \"${_step3_upload_mode}\""
  _step3_cli_mode="$(echo "${RELEASE_MODE:-build-upload}" | tr '[:upper:]' '[:lower:]')"
  case "$_step3_cli_mode" in
    build|build-upload) _step3_cli_mode="upload" ;;
  esac
  echo "Step3 CommercialReleaseCli mode: ${_step3_cli_mode} (from RELEASE_MODE=${RELEASE_MODE:-build-upload})"
  HR_ARGS="$HR_ARGS -commercialReleaseMode \"${_step3_cli_mode}\""
  [ -n "${RELEASE_PLAN_FILE}" ] && [ -f "${RELEASE_PLAN_FILE}" ] && HR_ARGS="$HR_ARGS -releasePlanFile \"${RELEASE_PLAN_FILE}\""
  [ "${RELEASE_ACTIVATE:-false}" = "true" ] && HR_ARGS="$HR_ARGS -releaseActivate \"true\""
  [ -n "${RELEASE_COMPRESSION_OVERRIDE}" ] && HR_ARGS="$HR_ARGS -releaseCompressionOverride \"${RELEASE_COMPRESSION_OVERRIDE}\""
  [ -n "${RELEASE_ENCRYPTION_OVERRIDE}" ] && HR_ARGS="$HR_ARGS -releaseEncryptionOverride \"${RELEASE_ENCRYPTION_OVERRIDE}\""
  [ -n "${RELEASE_SIGNATURE_OVERRIDE}" ] && HR_ARGS="$HR_ARGS -releaseSignatureOverride \"${RELEASE_SIGNATURE_OVERRIDE}\""
  [ -n "${RELEASE_ROLLBACK_TARGET}" ] && HR_ARGS="$HR_ARGS -releaseRollbackTarget \"${RELEASE_ROLLBACK_TARGET}\""
  if [ "${RESOURCE_BUILD_ENABLED:-false}" = "true" ] || [ "${CONFIG_EXPORT_ENABLED:-false}" = "true" ]; then
    echo "跳过 Step3 单独预热（本构建 Step1/2 已拉起 Unity 编译）"
  else
    echo "Unity Editor 程序集预热（Step3）..."
    _warmup_unity || echo "⚠ Step3 预热非零退出（可继续）"
    sleep 3
  fi
  _run_unity CommercialReleaseCli.ExecuteFromCommandLine $HR_ARGS || exit $?
  echo "Step 3 完成"
else
  echo "Step 3 (热更发布) 已跳过"
fi

# Step 4: APK 打包 + 上传阿里云
if [ "${APK_BUILD_ENABLED:-false}" = "true" ]; then
  _log_stage "4" "APK 打包与上传" "执行 ApkReleaseUploadCli：构建 APK 并上传阿里云。"
  echo "=== Step 4: APK 打包 ==="
  export UNITY_PROJECT_PATH="${UNITY_PROJECT_PATH:-${GIT_WORKSPACE:-}}"
  export UNITY_VERSION="${UNITY_VERSION:-6000.3.8f1}"
  export VERSION_NAME="${VERSION_NAME:-${RELEASE_VERSION:-1.0.0}}"
  export VERSION_CODE="${VERSION_CODE:-1}"
  export APP_NAME="${APP_NAME:-GomeKu}"
  export OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-${APK_DIR:-}}"
  export GIT_BRANCH="${GIT_BRANCH:-main}"
  export PROJECT_ID="${PROJECT_ID:-GomeKu}"
  export VERSION_STAGE="${VERSION_STAGE:-dev}"
  APK_SCRIPT="$(_resolve_apk_build_script || true)"
  if [ -z "$APK_SCRIPT" ]; then
    echo "ERROR: APK 步骤已启用但未找到 build_gameku_android.sh"
    exit 1
  fi
  bash "$APK_SCRIPT" || exit $?
  echo "=== Step 4b: APK 上传阿里云 ==="
  echo "上传: Unity 项目 Assets/Editor/Configs/OSSConfig.json (aliyun-oss)"
  APK_SEARCH="${OUTPUT_BASE_DIR:-${APK_DIR:-}}"
  APK_FILE=""
  if [ -n "$APK_SEARCH" ] && [ -d "$APK_SEARCH" ]; then
    APK_FILE=$(find "$APK_SEARCH" -name "*.apk" -type f -print0 2>/dev/null | xargs -0 ls -t 2>/dev/null | head -n 1)
  fi
  if [ -z "$APK_FILE" ] || [ ! -f "$APK_FILE" ]; then
    echo "⚠ 未找到 APK 文件，搜索目录: $APK_SEARCH"
    exit 1
  fi
  echo "APK 文件: $APK_FILE"
  APK_UP_ARGS="-apkFile \"$APK_FILE\""
  APK_UP_ARGS="$APK_UP_ARGS -releaseVersion \"${RELEASE_VERSION:-${VERSION_NAME:-1.0.0}}\""
  APK_UP_ARGS="$APK_UP_ARGS -releaseEnvironment \"${RELEASE_ENVIRONMENT:-Development}\""
  APK_UP_ARGS="$APK_UP_ARGS -releaseChannel \"${RELEASE_CHANNEL:-common}\""
  APK_UP_ARGS="$APK_UP_ARGS -releasePlatform \"${RELEASE_PLATFORM:-Android}\""
  APK_UP_ARGS="$APK_UP_ARGS -projectRoot \"${RELEASE_PROJECT_ROOT:-MyGame1}\""
  APK_UP_ARGS="$APK_UP_ARGS -appName \"${APP_NAME:-GomeKu}\""
  APK_UP_ARGS="$APK_UP_ARGS -versionCode \"${VERSION_CODE}\""
  export VERSION_CODE APP_NAME VERSION_NAME PROJECT_ID
  UNITY_LOG="${UNITY_LOG:-${JENKINS_HOME:-}/workspace/Android/unity_apk_upload.log}"
  export UNITY_LOG
  _run_unity ApkReleaseUploadCli.ExecuteFromCommandLine $APK_UP_ARGS || exit $?
  echo "=== Step 4c: APK 本地落盘 + 版本下载信息 ==="
  ARCHIVE_SCRIPT="${JENKINS_HOME:-}/scripts/archive_apk_after_build.py"
  [ -f "$ARCHIVE_SCRIPT" ] || ARCHIVE_SCRIPT="$(dirname "$0")/archive_apk_after_build.py"
  if [ -f "$ARCHIVE_SCRIPT" ]; then
  export APK_FILE
  export VERSION_CHANNEL_ID="${VERSION_CHANNEL_ID:-${CHANNEL:-}}"
  export OSS_APK_REMOTE_KEY="${RELEASE_PROJECT_ROOT:-MyGame1}/${RELEASE_ENVIRONMENT:-Development}/${RELEASE_CHANNEL:-wechat}/${RELEASE_PLATFORM:-android}/apk/${APP_NAME}_${VERSION_NAME:-1.0.0}_vc${VERSION_CODE}.apk"
  export BUILD_NUMBER="${BUILD_NUMBER:-}"
  python3 "$ARCHIVE_SCRIPT" || { echo "ERROR: APK 本地归档失败"; exit 1; }
  else
    echo "ERROR: 未找到 archive_apk_after_build.py，无法写入版本落盘"
    exit 1
  fi
  echo "Step 4 完成（含 APK 上传与落盘）"
else
  echo "Step 4 (APK打包) 已跳过"
fi

_log_stage "END" "流水线结束" "所有启用阶段已执行完成，可根据各阶段日志定位失败点。"

echo "======= 流水线执行完毕 ======="
