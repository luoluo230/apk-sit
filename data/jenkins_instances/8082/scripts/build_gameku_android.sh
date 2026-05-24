#!/bin/bash

echo "========================================="
echo "  GameKu Android 打包工具 (Jenkins)"
echo "========================================="
echo ""

# ========================================
# 环境变量配置
# ========================================

UNITY_PROJECT_PATH="${UNITY_PROJECT_PATH:-$HOME/Desktop/MyGame/GameKu}"
UNITY_VERSION="${UNITY_VERSION:-6000.3.8f1}"
VERSION_NAME="${VERSION_NAME:-1.0.0}"
VERSION_CODE="${VERSION_CODE:-100}"
APP_NAME="${APP_NAME:-GameKu}"
OUTPUT_BASE_DIR="${OUTPUT_BASE_DIR:-/Users/wangling/Desktop/Builds}"
# Git 分支：如果未指定或为空，则使用当前分支（不切换）
GIT_BRANCH="${GIT_BRANCH:-}"
JENKINS_WORKSPACE="${JENKINS_WORKSPACE:-$HOME/.jenkins/workspace/Android}"
LAST_PARAMS_FILE="$HOME/.jenkins/jobs/Android/last_params.txt"

# ========================================
# 生成构建输出文件夹
# ========================================

TIMESTAMP=$(date +"%Y%m%d_%H%M%S")
BUILD_OUTPUT_DIR="$OUTPUT_BASE_DIR/${APP_NAME}_${VERSION_NAME}_${TIMESTAMP}"
APK_DIR="$BUILD_OUTPUT_DIR"
LOG_DIR="$BUILD_OUTPUT_DIR/logs"

mkdir -p "$APK_DIR"
mkdir -p "$LOG_DIR"
mkdir -p "$JENKINS_WORKSPACE"

echo "配置:"
echo "  项目: $UNITY_PROJECT_PATH"
echo "  Unity: $UNITY_VERSION"
echo "  版本: $VERSION_NAME (code: $VERSION_CODE)"
echo "  应用名称: $APP_NAME"
echo "  输出基础目录: $OUTPUT_BASE_DIR"
echo "  构建输出目录: $BUILD_OUTPUT_DIR"
echo "  Jenkins 工作空间: $JENKINS_WORKSPACE"
echo "  Git 分支: ${GIT_BRANCH:-默认}"
echo ""

# ========================================
# 开始捕获日志
# ========================================

LOG_FILE="$LOG_DIR/build.log"
echo "📝 日志文件: $LOG_FILE"

# 记录构建开始时间（用于计算构建时长）
BUILD_START_TIME=$(date +%s)

exec > >(tee -a "$LOG_FILE") 2>&1

echo "========================================="
echo "  构建开始时间: $(date)"
echo "========================================="
echo ""

# ========================================
# 清理旧的 Unity 构建缓存
# ========================================

echo "步骤 1: 清理旧的 Unity 构建缓存"
rm -rf "$UNITY_PROJECT_PATH/Library/Bee/Android" 2>/dev/null || true
rm -rf "$UNITY_PROJECT_PATH/Builds/Android" 2>/dev/null || true
echo "✅ 已清理 Bee/Android 缓存"
echo ""

# ========================================
# 查找 Unity
# ========================================

echo "步骤 2: 查找 Unity 版本"
UNITY_PATH=""
for path in "/Applications/Unity/Unity-$UNITY_VERSION/Unity.app" \
            "/Applications/Unity/Hub/Editor/$UNITY_VERSION/Unity.app"; do
    if [ -d "$path" ]; then
        UNITY_PATH="$path"
        break
    fi
done

if [ -z "$UNITY_PATH" ]; then
    echo "❌ Unity $UNITY_VERSION 未找到"
    exit 1
fi

echo "✅ Unity: $UNITY_PATH"
echo ""

# ========================================
# Git 更新
# ========================================

echo "步骤 3: Git 更新"
cd "$UNITY_PROJECT_PATH"

GIT_COMMIT=""
CURRENT_BRANCH=""

if [ -d ".git" ]; then
    echo "📥 拉取代码..."

    # 如果未指定分支或指定为 main，则使用当前分支（不切换）
if [ -n "$GIT_BRANCH" ] && [ "$GIT_BRANCH" != "main" ] && [ "$GIT_BRANCH" != "$(git branch --show-current)" ]; then
        echo "切换到分支: $GIT_BRANCH"
        git fetch origin
        git checkout "$GIT_BRANCH" 2>/dev/null || true
    fi

    CURRENT_BRANCH=$(git branch --show-current)
    git fetch origin "$CURRENT_BRANCH" 2>/dev/null || true
    git pull origin "$CURRENT_BRANCH" 2>/dev/null || true

    GIT_COMMIT=$(git rev-parse --short HEAD)
    GIT_HEAD=$(git rev-parse HEAD)

    echo "✅ Git 更新完成"
    echo "   分支: $CURRENT_BRANCH"
    echo "   提交: $GIT_COMMIT"
else
    echo "⚠️  不是 Git 仓库，跳过更新"
fi

echo ""

# ========================================
# 生成 Unity 构建脚本（正确版本）
# ========================================

echo "步骤 4: 生成 Unity 构建脚本"
mkdir -p "$UNITY_PROJECT_PATH/Assets/Editor"

# 清理 Android Java 插件 BOM，避免 Gradle compileReleaseJavaWithJavac 失败
if [ -d "$UNITY_PROJECT_PATH/Assets/Plugins/Android" ]; then
  python3 - <<'PY' "$UNITY_PROJECT_PATH/Assets/Plugins/Android"
import pathlib, sys
root = pathlib.Path(sys.argv[1])
fixed = 0
for p in root.rglob("*.java"):
    data = p.read_bytes()
    if data.startswith(b"\xef\xbb\xbf"):
        p.write_bytes(data[3:])
        fixed += 1
if fixed:
    print(f"已移除 {fixed} 个 Java 文件的 UTF-8 BOM")
PY
fi

cat > "$UNITY_PROJECT_PATH/Assets/Editor/AndroidBuildScript.cs" << 'EOF'
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;
using System.Linq;

public class GameKuAndroidBuildScript
{
    public static void BuildAndroid()
    {
        UnityEngine.Debug.Log("=====================================");
        UnityEngine.Debug.Log("  Android 构建配置（强制设置）");
        UnityEngine.Debug.Log("=====================================");

        // ========== 强制设置 Android 配置 ==========

        // 1. 设置 ABI（架构）- ARM64 (arm64-v8a)，Unity 6 使用 PlayerSettings.Android.targetArchitectures
        PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
        UnityEngine.Debug.Log("✅ 架构: ARM64 (arm64-v8a)");

        PlayerSettings.Android.optimizedFramePacing = false;
        UnityEngine.Debug.Log("✅ 已禁用 optimizedFramePacing（避免 swappy STL 冲突）");

        // 2. 禁用 APK per CPU architecture
        // PlayerSettings.Android.buildApkPerCpuArchitecture = false;

        // ========== 获取场景 ==========

        string[] scenes = EditorBuildSettings.scenes
            .Where(scene => scene.enabled)
            .Select(scene => scene.path)
            .ToArray();

        if (scenes.Length == 0) {
            UnityEngine.Debug.LogError("❌ 没有找到启用的场景！");
            UnityEngine.Debug.LogError("请在 File > Build Settings 中添加场景。");
            EditorApplication.Exit(1);
            return;
        }

        UnityEngine.Debug.Log($"✅ 找到 {scenes.Length} 个场景");

        // ========== 配置构建参数 ==========

        BuildPlayerOptions opts = new BuildPlayerOptions();
        opts.scenes = scenes;
        opts.locationPathName = "Builds/Android/GameKu.apk";
        opts.target = BuildTarget.Android;
        opts.options = BuildOptions.None;

        // 从环境变量读取版本号
        string vc = System.Environment.GetEnvironmentVariable("VERSION_CODE") ?? "100";
        string vn = System.Environment.GetEnvironmentVariable("VERSION_NAME") ?? "1.0.0";
        string appName = System.Environment.GetEnvironmentVariable("APP_NAME") ?? "GameKu";

        UnityEngine.Debug.Log($"📦 版本参数:");
        UnityEngine.Debug.Log($"   版本代码: {vc}");
        UnityEngine.Debug.Log($"   版本号: {vn}");
        UnityEngine.Debug.Log($"   应用名称: {appName}");

        // 设置版本
        if (int.TryParse(vc, out int codeVal))
            PlayerSettings.Android.bundleVersionCode = codeVal;
        PlayerSettings.bundleVersion = vn;

        // 保存设置
        AssetDatabase.SaveAssets();

        UnityEngine.Debug.Log("🚀 开始 Android 构建...");
        UnityEngine.Debug.Log($"   输出: {opts.locationPathName}");

        // ---------- 开始构建 ----------
        BuildReport report = BuildPipeline.BuildPlayer(opts);
        BuildSummary summary = report.summary;

        if (summary.result == BuildResult.Succeeded) {
            UnityEngine.Debug.Log($"✅✅✅ 构建成功！");
            UnityEngine.Debug.Log($"   文件大小: {summary.totalSize} bytes");
            UnityEngine.Debug.Log($"   构建时间: {summary.totalTime.TotalSeconds:F2} 秒");
            UnityEngine.Debug.Log($"   错误数: {summary.totalErrors}");
            UnityEngine.Debug.Log($"   警告数: {summary.totalWarnings}");
            EditorApplication.Exit(0);
        } else {
            UnityEngine.Debug.LogError($"❌❌❌ 构建失败！");
            UnityEngine.Debug.LogError($"   错误数: {summary.totalErrors}");
            UnityEngine.Debug.LogError($"   警告数: {summary.totalWarnings}");
            EditorApplication.Exit(1);
        }
    }
}
EOF

echo "✅ Unity 构建脚本已生成"
echo ""

# ========================================
# Unity 构建
# ========================================

echo "步骤 5: Unity 构建（ARM64 架构）"
echo "开始构建，这可能需要 3-5 分钟..."
echo ""

UNITY_LOG_FILE="$LOG_DIR/unity_build.log"

VERSION_CODE="$VERSION_CODE" \
VERSION_NAME="$VERSION_NAME" \
APP_NAME="$APP_NAME" \
"$UNITY_PATH/Contents/MacOS/Unity" \
    -quit \
    -batchmode \
    -nographics \
    -projectPath "$UNITY_PROJECT_PATH" \
    -executeMethod GameKuAndroidBuildScript.BuildAndroid \
    -buildTarget Android \
    -logFile "$UNITY_LOG_FILE"

BUILD_EXIT_CODE=$?

if [ $BUILD_EXIT_CODE -eq 0 ]; then
    echo "✅ Unity 构建成功"
else
    BUILD_END_TIME=$(date +%s)
    BUILD_DURATION=$((BUILD_END_TIME - BUILD_START_TIME))
    BUILD_MINUTES=$((BUILD_DURATION / 60))
    BUILD_SECONDS=$((BUILD_DURATION % 60))

    echo ""
    echo "========================================="
    echo "❌ Android 版本 $VERSION_NAME 构建失败！"
    echo "========================================="
    echo ""
    echo "版本号: $VERSION_NAME"
    echo "构建时间: ${BUILD_MINUTES}分${BUILD_SECONDS}秒"
    echo "错误原因: Unity 构建失败（退出码: $BUILD_EXIT_CODE）"
    echo ""
    echo "构建日志（最后部分）:"
    tail -30 "$UNITY_LOG_FILE"
    echo ""
    echo "请检查构建日志并重试"

    exit 1
fi

echo ""

# ========================================
# 处理 APK
# ========================================

echo "步骤 6: 处理 APK 文件"

APK_PATH="$UNITY_PROJECT_PATH/Builds/Android/GameKu.apk"
APK_FINAL_NAME="${APP_NAME}_${VERSION_NAME}.apk"
APK_FINAL_PATH="$APK_DIR/$APK_FINAL_NAME"

if [ -f "$APK_PATH" ]; then
    APK_SIZE=$(du -h "$APK_PATH" | cut -f1)
    cp "$APK_PATH" "$APK_FINAL_PATH"

    echo "✅ APK 生成成功！"
    echo "   原始路径: $APK_PATH"
    echo "   最终路径: $APK_FINAL_PATH"
    echo "   文件大小: $APK_SIZE"
    ls -lh "$APK_FINAL_PATH"
else
    FIND=$(find "$UNITY_PROJECT_PATH/Builds" -name "*.apk" 2>/dev/null | head -1)
    if [ -n "$FIND" ]; then
        echo "⚠️  APK 在其他位置: $FIND"
        cp "$FIND" "$APK_FINAL_PATH"
        APK_SIZE=$(du -h "$APK_FINAL_PATH" | cut -f1)
        echo "✅ APK 已复制到: $APK_FINAL_PATH"
        echo "   文件大小: $APK_SIZE"
    else
        BUILD_END_TIME=$(date +%s)
        BUILD_DURATION=$((BUILD_END_TIME - BUILD_START_TIME))
        BUILD_MINUTES=$((BUILD_DURATION / 60))
        BUILD_SECONDS=$((BUILD_DURATION % 60))

        echo ""
        echo "========================================="
        echo "❌ Android 版本 $VERSION_NAME 构建失败！"
        echo "========================================="
        echo ""
        echo "版本号: $VERSION_NAME"
        echo "构建时间: ${BUILD_MINUTES}分${BUILD_SECONDS}秒"
        echo "错误原因: 未找到 APK 文件"
        echo ""
        echo "构建日志（最后部分）:"
        tail -30 "$UNITY_LOG_FILE"
        echo ""
        echo "请检查构建日志并重试"

        exit 1
    fi
fi

echo ""

# ========================================
# 生成构建信息文件
# ========================================

echo "步骤 7: 生成构建信息文件"

cat > "$BUILD_OUTPUT_DIR/BUILD_INFO.md" << EOF
# 构建信息

## 基本信息
- **应用名称**: $APP_NAME
- **版本号**: $VERSION_NAME
- **版本代码**: $VERSION_CODE
- **构建时间**: $(date +"%Y-%m-%d %H:%M:%S")
- **构建类型**: Android
- **架构**: ARM64 (arm64-v8a)

## Unity 信息
- **Unity 版本**: $UNITY_VERSION
- **项目路径**: $UNITY_PROJECT_PATH

## Git 信息
- **分支**: ${CURRENT_BRANCH:-N/A}
- **提交**: ${GIT_COMMIT:-N/A}
- **完整 SHA**: ${GIT_HEAD:-N/A}

## 输出文件
- **APK 路径**: $APK_FINAL_PATH
- **APK 大小**: $APK_SIZE

EOF

echo "✅ 构建信息已生成"
echo ""

# ========================================
# 复制 APK 到 Jenkins 工作空间
# ========================================

echo "步骤 8: 复制 APK 到 Jenkins 工作空间"

JENKINS_APK="${JENKINS_WORKSPACE}/${APP_NAME}_${VERSION_NAME}.apk"

if [ -f "$APK_FINAL_PATH" ]; then
    cp "$APK_FINAL_PATH" "$JENKINS_APK"
    echo "✅ APK 已复制到 Jenkins 工作空间"
    echo "   Jenkins 工作空间: $JENKINS_APK"
    ls -lh "$JENKINS_APK"

    # 复制到输出根目录
    cp "$APK_FINAL_PATH" "$OUTPUT_BASE_DIR/${APP_NAME}_${VERSION_NAME}.apk"
    echo "✅ APK 也已复制到输出根目录"

    # 复制到 HTTP 服务器目录
    HTTP_DIR="${HOME}/Downloads/APK_Builds"
    mkdir -p "$HTTP_DIR"
    cp "$APK_FINAL_PATH" "$HTTP_DIR/${APP_NAME}_${VERSION_NAME}.apk"
    chmod 644 "$HTTP_DIR/${APP_NAME}_${VERSION_NAME}.apk"
    echo "✅ APK 也已复制到 HTTP 服务器目录 for download ($HTTP_DIR)"
else
    BUILD_END_TIME=$(date +%s)
    BUILD_DURATION=$((BUILD_END_TIME - BUILD_START_TIME))
    BUILD_MINUTES=$((BUILD_DURATION / 60))
    BUILD_SECONDS=$((BUILD_DURATION % 60))

    echo ""
    echo "========================================="
    echo "❌ Android 版本 $VERSION_NAME 构建失败！"
    echo "========================================="
    echo ""
    echo "版本号: $VERSION_NAME"
    echo "构建时间: ${BUILD_MINUTES}分${BUILD_SECONDS}秒"
    echo "错误原因: APK 复制失败，原始文件不存在"
    echo ""
    echo "请检查构建日志并重试"

    exit 1
fi

echo ""

# ========================================
# 记录本次构建参数（供下次使用）
# ========================================

echo "步骤 9: 保存构建参数"

cat > "$LAST_PARAMS_FILE" << PARAMS_EOF
UNITY_VERSION=$UNITY_VERSION
VERSION_NAME=$VERSION_NAME
VERSION_CODE=$VERSION_CODE
APP_NAME=$APP_NAME
OUTPUT_BASE_DIR=$OUTPUT_BASE_DIR
GIT_BRANCH=$GIT_BRANCH
BUILD_TIME=$(date +%Y-%m-%d_%H%M%S)
PARAMS_EOF

echo "✅ 构建参数已保存到: $LAST_PARAMS_FILE"
echo ""

# ========================================
# 计算构建时间
# ========================================

BUILD_END_TIME=$(date +%s)
BUILD_DURATION=$((BUILD_END_TIME - BUILD_START_TIME))
BUILD_MINUTES=$((BUILD_DURATION / 60))
BUILD_SECONDS=$((BUILD_DURATION % 60))

# ========================================
# 完成总结（用户要求的格式）
# ========================================

echo ""
echo "========================================="
echo "✅ Android 版本 $VERSION_NAME 构建成功！"
echo "========================================="
echo ""
echo "版本号: $VERSION_NAME"
echo "构建时间: ${BUILD_MINUTES}分${BUILD_SECONDS}秒"
echo "构建状态: SUCCESS"
# 与 apk-site 一致：优先读 .apk-site-base-url，再退回到 apk-site 主站 /pub/download/
DOWNLOAD_BASE=""
[ -f "${OUTPUT_BASE_DIR}/.apk-site-base-url" ] && DOWNLOAD_BASE=$(head -1 "${OUTPUT_BASE_DIR}/.apk-site-base-url" | tr -d '\r\n')
[ -z "$DOWNLOAD_BASE" ] && DOWNLOAD_BASE="http://192.168.0.106:5003"
echo "📱 下载链接: ${DOWNLOAD_BASE}/pub/download/${APP_NAME}_${VERSION_NAME}.apk"
echo ""

exit 0
