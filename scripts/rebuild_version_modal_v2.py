#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V2: Card-based version modal with functional grouping."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.data import channels_db

channel_opts = ''.join(
    '<option value="%s">%s</option>' % (c.get('id',''), c.get('name',c.get('id','')))
    for c in (channels_db if isinstance(channels_db, list) else []) if c.get('id')
) or '<option value="dev">开发</option><option value="test">测试</option><option value="production">线上</option>'

with open('routes/admin_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_start = '<div id="versionModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-start justify-center z-50 p-6 pt-12"'
old_end = '<div id="projectQRModal"'

new_modal = (
'<div id="versionModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-start justify-center z-50 p-4 pt-8" onclick="if(event.target===this) closeVersionModal()">\n'
'    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[92vh] overflow-hidden flex flex-col border border-slate-100" onclick="event.stopPropagation()">\n'
'        <div class="px-5 py-2.5 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-indigo-50 flex items-center justify-between shrink-0">\n'
'            <h3 class="font-semibold text-slate-900 text-base" id="versionModalTitle">新建版本</h3>\n'
'            <button onclick="closeVersionModal()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>\n'
'        </div>\n'
'        <div class="px-5 py-3 overflow-y-auto flex-1 space-y-3">\n'
'            <input type="hidden" id="versionEditId" value="">\n'

# ===== Commercial mode toggle =====
'            <label class="flex items-center gap-3 p-2.5 rounded-xl border-2 border-slate-200 cursor-pointer hover:border-violet-300 transition bg-white" id="labelCommercialMode">\n'
'                <input type="checkbox" id="chkCommercialMode" class="rounded text-violet-600 focus:ring-violet-500 w-4 h-4" onchange="toggleCommercialMode()">\n'
'                <div class="flex-1">\n'
'                    <span class="font-medium text-sm text-slate-700">高级商业版本</span>\n'
'                    <p class="text-[11px] text-slate-400">启用可插拔构建流水线：配置导出 → 资源打包 → 热更发布 → APK打包</p>\n'
'                </div>\n'
'            </label>\n'

# ===== Card 1: 版本标识 =====
'            <div class="rounded-xl border border-slate-200 bg-white overflow-hidden">\n'
'                <div class="px-4 py-2 bg-slate-50 border-b border-slate-100 flex items-center gap-2">\n'
'                    <span class="w-6 h-6 rounded-lg bg-indigo-100 text-indigo-600 flex items-center justify-center text-xs"><i class="fas fa-tag"></i></span>\n'
'                    <span class="text-sm font-semibold text-slate-700">版本标识</span>\n'
'                    <span class="text-[11px] text-slate-400">唯一确定一个版本的渠道、阶段、平台和编号</span>\n'
'                </div>\n'
'                <div class="p-4">\n'
'                    <div class="grid grid-cols-6 gap-2">\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">渠道 <span class="text-rose-400">*</span></label><select id="versionChannel" onchange="suggestVersionApkPath()" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-1 focus:ring-indigo-500/30">' + channel_opts + '</select></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">阶段 <span class="text-rose-400">*</span></label><select id="versionStage" onchange="suggestVersionApkPath()" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-1 focus:ring-indigo-500/30"><option value="dev">开发</option><option value="test">测试</option><option value="production">线上</option></select></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">平台 <span class="text-rose-400">*</span></label><select id="versionPlatform" onchange="suggestVersionApkPath();syncVersionPlatformFields()" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-1 focus:ring-indigo-500/30"><option value="android">Android</option><option value="ios">iOS</option></select></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">版本名 <span class="text-rose-400">*</span></label><input id="versionName" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm focus:ring-1 focus:ring-indigo-500/30" placeholder="1.0.0" value="1.0.0"></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">Version Code</label><input id="versionCode" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm focus:ring-1 focus:ring-indigo-500/30" placeholder="100" value="100"></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">状态</label><select id="versionStatus" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white focus:ring-1 focus:ring-indigo-500/30"><option value="active">有效</option><option value="testing">测试中</option><option value="deprecated">废弃</option><option value="archived">归档</option></select></div>\n'
'                    </div>\n'
'                </div>\n'
'            </div>\n'

# ===== Card 2: 包体配置 =====
'            <div class="rounded-xl border border-slate-200 bg-white overflow-hidden">\n'
'                <div class="px-4 py-2 bg-slate-50 border-b border-slate-100 flex items-center gap-2">\n'
'                    <span class="w-6 h-6 rounded-lg bg-amber-100 text-amber-600 flex items-center justify-center text-xs"><i class="fas fa-box"></i></span>\n'
'                    <span class="text-sm font-semibold text-slate-700">包体配置</span>\n'
'                    <span class="text-[11px] text-slate-400">安装包路径、分发方式及平台相关参数</span>\n'
'                </div>\n'
'                <div class="p-4 space-y-2">\n'
'                    <div class="grid grid-cols-3 gap-2">\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">发布方式</label><select id="versionDistributionMethod" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white"><option value="direct">直接下载</option><option value="enterprise">企业分发</option><option value="store">应用商店</option><option value="testflight">TestFlight</option><option value="internal">内部包体</option></select></div>\n'
'                        <div id="androidVersionFields"><label class="block text-[11px] text-slate-400 mb-0.5">包名</label><input id="versionPackageName" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="com.example.app"></div>\n'
'                        <div id="androidSdkField"><label class="block text-[11px] text-slate-400 mb-0.5">最低SDK</label><input id="versionMinSdk" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="24" value="24"></div>\n'
'                        <div id="iosVersionFields" class="hidden"><label class="block text-[11px] text-slate-400 mb-0.5">Bundle ID</label><input id="versionBundleId" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="com.example.iosapp"></div>\n'
'                        <div id="iosSdkField" class="hidden"><label class="block text-[11px] text-slate-400 mb-0.5">最低iOS</label><input id="versionMinIosVersion" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="16.4" value="16.4"></div>\n'
'                    </div>\n'
'                    <div class="grid grid-cols-3 gap-2">\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">安装包路径</label><input id="versionApkPath" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="输出或下载路径"></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">资源路径</label><input id="versionResourcePath" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="资源目录"></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">配置路径</label><input id="versionConfigPath" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="配置目录"></div>\n'
'                    </div>\n'
'                </div>\n'
'            </div>\n'

# ===== Card 3: 发布配置 =====
'            <div class="rounded-xl border border-slate-200 bg-white overflow-hidden">\n'
'                <div class="px-4 py-2 bg-slate-50 border-b border-slate-100 flex items-center gap-2">\n'
'                    <span class="w-6 h-6 rounded-lg bg-emerald-100 text-emerald-600 flex items-center justify-center text-xs"><i class="fas fa-paper-plane"></i></span>\n'
'                    <span class="text-sm font-semibold text-slate-700">发布配置</span>\n'
'                    <span class="text-[11px] text-slate-400">更新说明、构建参数与 Jenkins 关联</span>\n'
'                </div>\n'
'                <div class="p-4 grid grid-cols-2 gap-3">\n'
'                    <div class="space-y-2">\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">更新说明</label><textarea id="versionChangelog" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" rows="2" placeholder="与本版本匹配的APK共用此说明"></textarea></div>\n'
'                        <label class="flex items-center gap-1.5 text-sm"><input type="checkbox" id="versionChangelogRecommended" class="rounded"> 推荐版本</label>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">备注</label><textarea id="versionNotes" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" rows="1"></textarea></div>\n'
'                        <div><label class="block text-[11px] text-slate-400 mb-0.5">Jenkins Job ID</label><input id="versionJenkinsJob" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="可选"></div>\n'
'                    </div>\n'
'                    <div class="space-y-2">\n'
'                        <div class="grid grid-cols-2 gap-2">\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">Unity版本</label><input id="ppApkUnity" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" value="6000.3.8f1"></div>\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">Git分支</label><input id="ppApkBranch" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" value="main"></div>\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">APP_NAME</label><input id="ppApkAppName" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm"></div>\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">输出目录</label><input id="ppApkOutput" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm"></div>\n'
'                        </div>\n'
'                    </div>\n'
'                </div>\n'
'            </div>\n'

# ===== Pipeline (hidden by default) =====
'            <div id="versionPipeline" class="hidden rounded-xl border border-violet-200 bg-white overflow-hidden">\n'
'                <div class="px-4 py-2 bg-violet-50 border-b border-violet-100 flex items-center gap-2">\n'
'                    <span class="w-6 h-6 rounded-lg bg-violet-100 text-violet-600 flex items-center justify-center text-xs"><i class="fas fa-diagram-project"></i></span>\n'
'                    <span class="text-sm font-semibold text-violet-700">构建流水线</span>\n'
'                    <span class="text-[11px] text-violet-400">可插拔选择要执行的构建步骤，每个步骤按需启用</span>\n'
'                </div>\n'
'                <div class="p-4">\n'
'                    <div class="flex gap-1 bg-slate-100 rounded-lg p-1 mb-3" id="pipelineTabs">\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-xs font-medium transition bg-white text-slate-700 shadow-sm" data-ptab="config_export" onclick="switchPipelineTab(\'config_export\')"><span class="w-4 h-4 inline-flex items-center justify-center rounded-full bg-indigo-100 text-indigo-600 text-[9px] font-bold mr-1">1</span>配置导出</button>\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-xs font-medium transition text-slate-500" data-ptab="resource_build" onclick="switchPipelineTab(\'resource_build\')"><span class="w-4 h-4 inline-flex items-center justify-center rounded-full bg-slate-200 text-slate-500 text-[9px] font-bold mr-1">2</span>资源打包</button>\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-xs font-medium transition text-slate-500" data-ptab="hot_release" onclick="switchPipelineTab(\'hot_release\')"><span class="w-4 h-4 inline-flex items-center justify-center rounded-full bg-slate-200 text-slate-500 text-[9px] font-bold mr-1">3</span>热更发布</button>\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-xs font-medium transition text-slate-500" data-ptab="apk_build" onclick="switchPipelineTab(\'apk_build\')"><span class="w-4 h-4 inline-flex items-center justify-center rounded-full bg-slate-200 text-slate-500 text-[9px] font-bold mr-1">4</span>APK打包</button>\n'
'                    </div>\n'

# Tab 1: 配置导出
'                    <div id="ptabConfigExport" class="pipeline-panel">\n'
'                        <label class="flex items-center gap-2 mb-2"><input type="checkbox" id="ppConfigExport" class="rounded" checked onchange="togglePipelineStepUI(\'config_export\')"> <span class="text-sm font-medium text-slate-700">配置导出发布</span> <span class="text-[11px] text-slate-400">— ConfigRemotePublish：Excel导表→manifest→上传OSS</span></label>\n'
'                        <div id="ppConfigExportBody" class="grid grid-cols-3 gap-2 bg-slate-50 rounded-lg p-3">\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">远端路径前缀 <span class="text-rose-400">*</span></label><input id="ppCfgPrefix" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" value="config-release"></div>\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">客户端版本</label><input id="ppCfgClientVer" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" value="1.0.0"></div>\n'
'                            <div class="flex items-end pb-1.5"><label class="flex items-center gap-1 text-sm"><input type="checkbox" id="ppCfgIncludeCode"> 含代码产物</label></div>\n'
'                        </div>\n'
'                    </div>\n'

# Tab 2: 资源打包
'                    <div id="ptabResourceBuild" class="pipeline-panel hidden">\n'
'                        <label class="flex items-center gap-2 mb-2"><input type="checkbox" id="ppResourceBuild" class="rounded" checked onchange="togglePipelineStepUI(\'resource_build\')"> <span class="text-sm font-medium text-slate-700">资源打包</span> <span class="text-[11px] text-slate-400">— ResourcePipelineWorkbench：扫描→依赖→规则→构建→标准化产物</span></label>\n'
'                        <div id="ppResourceBuildBody" class="grid grid-cols-2 gap-2 bg-slate-50 rounded-lg p-3">\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">构建引擎 <span class="text-rose-400">*</span></label><select id="ppResProvider" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white"><option value="addressables-v2">Addressables v2（推荐）</option><option value="legacy-bundle-builder">Legacy</option></select></div>\n'
'                            <div><label class="block text-[11px] text-slate-400 mb-0.5">场景方案</label><input id="ppResScenario" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" value="default"></div>\n'
'                        </div>\n'
'                    </div>\n'

# Tab 3: 热更发布
'                    <div id="ptabHotRelease" class="pipeline-panel hidden">\n'
'                        <label class="flex items-center gap-2 mb-2"><input type="checkbox" id="ppHotRelease" class="rounded" checked onchange="togglePipelineStepUI(\'hot_release\')"> <span class="text-sm font-medium text-slate-700">代码+资源热更发布</span> <span class="text-[11px] text-slate-400">— CommercialReleaseCli：压缩→加密→签名→上传OSS→激活/灰度/回滚</span></label>\n'
'                        <div id="ppHotReleaseBody" class="space-y-2 bg-slate-50 rounded-lg p-3">\n'
'                            <div class="flex flex-wrap items-center gap-3">\n'
'                                <span class="text-xs text-slate-500">发布对象 <span class="text-rose-400">*</span>:</span>\n'
'                                <span id="ppChipCode" class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-blue-100 text-blue-700 border-2 border-blue-300 cursor-pointer select-none" onclick="togglePpChip(\'code\')"><i class="fas fa-code text-[9px]"></i>代码包</span>\n'
'                                <span id="ppChipResource" class="inline-flex items-center gap-1 px-2 py-1 rounded-full text-[11px] font-medium bg-emerald-100 text-emerald-700 border-2 border-emerald-300 cursor-pointer select-none" onclick="togglePpChip(\'resource\')"><i class="fas fa-cube text-[9px]"></i>资源包</span>\n'
'                            </div>\n'
'                            <div class="grid grid-cols-4 gap-2">\n'
'                                <div><label class="block text-[11px] text-slate-400 mb-0.5">渠道 <span class="text-rose-400">*</span></label><select id="ppHrChannel" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white"><option>common</option><option>official</option><option>tap</option><option>bilibili</option></select></div>\n'
'                                <div><label class="block text-[11px] text-slate-400 mb-0.5">热更标签</label><input id="ppHrLabels" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" value="hotupdate,aotmeta"></div>\n'
'                                <div><label class="block text-[11px] text-slate-400 mb-0.5">发布模式 <span class="text-rose-400">*</span></label><select id="ppHrMode" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white" onchange="onPpHrModeChange()"><option value="build-upload">构建并上传</option><option value="build">仅构建</option><option value="upload">仅上传</option><option value="activate">激活</option><option value="rollback">回滚</option></select></div>\n'
'                                <div><label class="block text-[11px] text-slate-400 mb-0.5">上传模式</label><select id="ppHrUpload" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm bg-white"><option value="incremental">增量</option><option value="full">全量</option></select></div>\n'
'                                <div id="ppHrRollbackWrap"><label class="block text-[11px] text-slate-400 mb-0.5">回滚目标</label><input id="ppHrRollback" class="w-full px-2 py-1.5 border border-slate-200 rounded text-sm" placeholder="回滚模式填写" disabled></div>\n'
'                            </div>\n'
'                            <div class="grid grid-cols-2 gap-2">\n'
'                                <div class="rounded-lg p-2 bg-blue-50/60 border border-blue-100">\n'
'                                    <p class="text-[11px] font-semibold text-blue-700 mb-1"><i class="fas fa-code mr-1"></i>代码包策略</p>\n'
'                                    <div class="grid grid-cols-2 gap-1">\n'
'                                        <div><label class="text-[10px] text-slate-400">启用</label><input type="checkbox" id="ppHrCodeEnabled" class="rounded" checked></div>\n'
'                                        <div><label class="text-[10px] text-slate-400">压缩</label><select id="ppHrCodeComp" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option>Zip</option><option>None</option><option>Lz4</option></select></div>\n'
'                                        <div><label class="text-[10px] text-slate-400">加密</label><select id="ppHrCodeEnc" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option>Aes</option><option>None</option><option>Xor</option></select></div>\n'
'                                        <div><label class="text-[10px] text-slate-400">签名</label><select id="ppHrCodeSig" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option value="builtin-signature">启用</option><option value="">关闭</option></select></div>\n'
'                                        <div class="col-span-2"><label class="text-[10px] text-slate-400">包单元</label><input id="ppHrCodeUnits" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px]" value="aotmeta, hotupdate, scriptpatch, symbols"></div>\n'
'                                    </div>\n'
'                                </div>\n'
'                                <div class="rounded-lg p-2 bg-emerald-50/60 border border-emerald-100">\n'
'                                    <p class="text-[11px] font-semibold text-emerald-700 mb-1"><i class="fas fa-cube mr-1"></i>资源包策略</p>\n'
'                                    <div class="grid grid-cols-2 gap-1">\n'
'                                        <div><label class="text-[10px] text-slate-400">启用</label><input type="checkbox" id="ppHrResEnabled" class="rounded" checked></div>\n'
'                                        <div><label class="text-[10px] text-slate-400">压缩</label><select id="ppHrResComp" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option>None</option><option>Zip</option><option>Lz4</option></select></div>\n'
'                                        <div><label class="text-[10px] text-slate-400">加密</label><select id="ppHrResEnc" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option>None</option><option>Aes</option></select></div>\n'
'                                        <div><label class="text-[10px] text-slate-400">签名</label><select id="ppHrResSig" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option value="builtin-signature">启用</option><option value="">关闭</option></select></div>\n'
'                                        <div class="col-span-2"><label class="text-[10px] text-slate-400">包单元</label><input id="ppHrResUnits" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px]" value="addressable, hotupdate, optional, platform, hd, streaming"></div>\n'
'                                    </div>\n'
'                                </div>\n'
'                            </div>\n'
'                            <details><summary class="cursor-pointer text-[11px] text-slate-400 hover:text-slate-600">高级覆盖选项</summary><div class="grid grid-cols-3 gap-2 mt-1"><div class="col-span-1"><label class="text-[10px] text-slate-400">压缩覆盖</label><select id="ppHrCompOvr" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option value="">默认</option><option>Zip</option><option>Lz4</option><option>None</option></select></div><div><label class="text-[10px] text-slate-400">加密覆盖</label><select id="ppHrEncOvr" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option value="">默认</option><option>Aes</option><option>Xor</option><option>None</option></select></div><div><label class="text-[10px] text-slate-400">签名覆盖</label><select id="ppHrSigOvr" class="w-full px-1.5 py-1 border border-slate-200 rounded text-[10px] bg-white"><option value="">默认</option><option value="builtin-signature">启用</option></select></div></div></details>\n'
'                        </div>\n'
'                    </div>\n'

# Tab 4: APK打包
'                    <div id="ptabApkBuild" class="pipeline-panel hidden">\n'
'                        <label class="flex items-center gap-2 mb-2"><input type="checkbox" id="ppApkBuild" class="rounded" onchange="togglePipelineStepUI(\'apk_build\')"> <span class="text-sm font-medium text-slate-700">APK 打包上传</span> <span class="text-[11px] text-slate-400">— Unity BuildPipeline：编译打包→签名→上传分发</span></label>\n'
'                        <div id="ppApkBuildBody" class="hidden bg-slate-50 rounded-lg p-3">\n'
'                            <p class="text-[11px] text-slate-400">APK 打包参数已在上方「包体配置」与「发布配置」中设置，此处仅控制是否执行。</p>\n'
'                        </div>\n'
'                    </div>\n'
'                </div>\n'
'            </div>\n'
'        </div>\n'
'        <div class="px-5 py-2.5 border-t border-slate-100 bg-slate-50 flex justify-end gap-2 shrink-0">\n'
'            <button type="button" onclick="closeVersionModal()" class="px-4 py-2 border border-slate-200 rounded-lg text-sm text-slate-700 hover:bg-slate-50">取消</button>\n'
'            <button type="button" onclick="saveVersion()" class="px-5 py-2 bg-indigo-600 text-white rounded-lg text-sm font-medium hover:bg-indigo-700 shadow-sm">保存版本</button>\n'
'        </div>\n'
'    </div>\n'
'</div>\n'
)

idx_start = content.find(old_start)
idx_end = content.find(old_end, idx_start)
if idx_start >= 0 and idx_end > 0:
    content = content[:idx_start] + new_modal + content[idx_end:]
    print('Replaced version modal V2 successfully')
else:
    print('Markers not found:', idx_start, idx_end)

with open('routes/admin_routes.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
