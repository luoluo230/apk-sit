#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""V3: Ultra-compact version modal."""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from models.data import channels_db

channel_opts = ''.join(
    '<option value="%s">%s</option>' % (c.get('id',''), c.get('name',c.get('id','')))
    for c in (channels_db if isinstance(channels_db, list) else []) if c.get('id')
) or '<option value="dev">开发</option><option value="test">测试</option><option value="production">线上</option>'

with open('routes/admin_routes.py', 'r', encoding='utf-8') as f:
    content = f.read()

old_start = '<div id="versionModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-start justify-center z-50 p-4 pt-8"'
old_end = '<div id="projectQRModal"'

# Field component: compact row with tiny label + small input
def F(label, input_html, required=False):
    star = '<span class="text-rose-400">*</span>' if required else ''
    return f'<div><span class="text-[10px] text-slate-400">{star}{label}</span>{input_html}</div>'

# Select input
def S(id, opts, extra=''):
    return f'<select id="{id}" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white focus:ring-1 focus:ring-indigo-500/30"{extra}>{opts}</select>'

# Text input  
def T(id, val='', placeholder='', extra=''):
    return f'<input id="{id}" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs focus:ring-1 focus:ring-indigo-500/30" value="{val}" placeholder="{placeholder}"{extra}>'

new_modal = (
'<div id="versionModal" class="hidden fixed inset-0 bg-slate-900/60 backdrop-blur-sm flex items-start justify-center z-50 p-3 pt-6" onclick="if(event.target===this) closeVersionModal()">\n'
'    <div class="bg-white rounded-2xl shadow-2xl w-full max-w-4xl max-h-[94vh] overflow-hidden flex flex-col border border-slate-100" onclick="event.stopPropagation()">\n'
'        <div class="px-4 py-2 border-b border-slate-100 bg-gradient-to-r from-slate-50 to-indigo-50 flex items-center justify-between shrink-0">\n'
'            <h3 class="font-semibold text-slate-900 text-sm" id="versionModalTitle">新建版本</h3>\n'
'            <button onclick="closeVersionModal()" class="text-slate-400 hover:text-slate-600"><i class="fas fa-times"></i></button>\n'
'        </div>\n'
'        <div class="px-4 py-2 overflow-y-auto flex-1" style="display:grid;gap:8px;">\n'
'            <input type="hidden" id="versionEditId" value="">\n'

# Commercial mode toggle
'            <label class="flex items-center gap-2 px-3 py-2 rounded-lg border-2 border-slate-200 cursor-pointer hover:border-violet-300 transition bg-white" id="labelCommercialMode" style="margin:0;">\n'
'                <input type="checkbox" id="chkCommercialMode" style="width:16px;height:16px;accent-color:#7c3aed;" onchange="toggleCommercialMode()">\n'
'                <span class="text-sm font-medium text-slate-700">高级商业版本</span>\n'
'                <span class="text-[11px] text-slate-400 ml-2 hidden sm:inline">可插拔流水线：配置导出→资源打包→热更发布→APK打包</span>\n'
'            </label>\n'

# Card 1: 版本标识
'            <div class="rounded-lg border border-slate-200 bg-white overflow-hidden" style="margin:0;">\n'
'                <div class="px-3 py-1.5 bg-slate-50/80 border-b border-slate-100 flex items-center gap-1.5">\n'
'                    <span class="w-5 h-5 rounded bg-indigo-100 text-indigo-600 flex items-center justify-center text-[10px]"><i class="fas fa-tag"></i></span>\n'
'                    <span class="text-xs font-semibold text-slate-600">版本标识</span>\n'
'                    <span class="text-[10px] text-slate-400 hidden sm:inline">渠道·阶段·平台·版本号</span>\n'
'                </div>\n'
'                <div class="p-3">\n'
'                    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;">\n'
+ F('渠道', S('versionChannel', channel_opts, ' onchange="suggestVersionApkPath()"'), True) +
+ F('阶段', S('versionStage', '<option value="dev">开发</option><option value="test">测试</option><option value="production">线上</option>', ' onchange="suggestVersionApkPath()"'), True) +
+ F('平台', S('versionPlatform', '<option value="android">Android</option><option value="ios">iOS</option>', ' onchange="suggestVersionApkPath();syncVersionPlatformFields()"'), True) +
+ F('版本名', T('versionName', '1.0.0', '1.0.0'), True) +
+ F('Version Code', T('versionCode', '100', '100')) +
+ F('状态', S('versionStatus', '<option value="active">有效</option><option value="testing">测试中</option><option value="deprecated">废弃</option><option value="archived">归档</option>')) +
'                    </div>\n'
'                </div>\n'
'            </div>\n'

# Card 2: 包体配置  
'            <div class="rounded-lg border border-slate-200 bg-white overflow-hidden" style="margin:0;">\n'
'                <div class="px-3 py-1.5 bg-slate-50/80 border-b border-slate-100 flex items-center gap-1.5">\n'
'                    <span class="w-5 h-5 rounded bg-amber-100 text-amber-600 flex items-center justify-center text-[10px]"><i class="fas fa-box"></i></span>\n'
'                    <span class="text-xs font-semibold text-slate-600">包体配置</span>\n'
'                    <span class="text-[10px] text-slate-400 hidden sm:inline">分发方式·包名·路径</span>\n'
'                </div>\n'
'                <div class="p-3">\n'
'                    <div style="display:grid;grid-template-columns:repeat(6,1fr);gap:8px;">\n'
+ F('发布方式', S('versionDistributionMethod', '<option value="direct">直接下载</option><option value="enterprise">企业分发</option><option value="store">应用商店</option><option value="testflight">TestFlight</option><option value="internal">内部包体</option>')) +
+ F('包名', T('versionPackageName', '', 'com.example.app')) +
+ F('最低SDK', T('versionMinSdk', '24', '24')) +
+ F('安装包路径', T('versionApkPath', '', '输出路径')) +
+ F('资源路径', T('versionResourcePath', '', '资源目录')) +
+ F('配置路径', T('versionConfigPath', '', '配置目录')) +
'                    </div>\n'
'                    <div id="androidVersionFields" style="display:none;"></div>\n'
'                    <div id="iosVersionFields" class="hidden" style="display:none;"></div>\n'
'                </div>\n'
'            </div>\n'

# Card 3: 发布配置
'            <div class="rounded-lg border border-slate-200 bg-white overflow-hidden" style="margin:0;">\n'
'                <div class="px-3 py-1.5 bg-slate-50/80 border-b border-slate-100 flex items-center gap-1.5">\n'
'                    <span class="w-5 h-5 rounded bg-emerald-100 text-emerald-600 flex items-center justify-center text-[10px]"><i class="fas fa-paper-plane"></i></span>\n'
'                    <span class="text-xs font-semibold text-slate-600">发布配置</span>\n'
'                    <span class="text-[10px] text-slate-400 hidden sm:inline">说明·参数·Jenkins</span>\n'
'                </div>\n'
'                <div class="p-3">\n'
'                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:8px;">\n'
'                        <div style="display:grid;gap:6px;align-content:start;">\n'
'                            <div><span class="text-[10px] text-slate-400">更新说明</span><textarea id="versionChangelog" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" rows="2" placeholder="与本版本匹配的APK共用此说明"></textarea></div>\n'
'                            <label class="flex items-center gap-1 text-xs"><input type="checkbox" id="versionChangelogRecommended" style="accent-color:#f59e0b;"> 推荐版本</label>\n'
'                            <div><span class="text-[10px] text-slate-400">备注</span><textarea id="versionNotes" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" rows="1"></textarea></div>\n'
'                            <div><span class="text-[10px] text-slate-400">Jenkins Job ID</span><input id="versionJenkinsJob" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" placeholder="可选"></div>\n'
'                        </div>\n'
'                        <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;align-content:start;">\n'
'                            <div><span class="text-[10px] text-slate-400">Unity版本</span><input id="ppApkUnity" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" value="6000.3.8f1"></div>\n'
'                            <div><span class="text-[10px] text-slate-400">Git分支</span><input id="ppApkBranch" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" value="main"></div>\n'
'                            <div><span class="text-[10px] text-slate-400">APP_NAME</span><input id="ppApkAppName" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs"></div>\n'
'                            <div><span class="text-[10px] text-slate-400">输出目录</span><input id="ppApkOutput" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs"></div>\n'
'                        </div>\n'
'                    </div>\n'
'                </div>\n'
'            </div>\n'

# Pipeline card (hidden)
'            <div id="versionPipeline" class="hidden rounded-lg border border-violet-200 bg-white overflow-hidden" style="margin:0;">\n'
'                <div class="px-3 py-1.5 bg-violet-50/80 border-b border-violet-100 flex items-center gap-1.5">\n'
'                    <span class="w-5 h-5 rounded bg-violet-100 text-violet-600 flex items-center justify-center text-[10px]"><i class="fas fa-diagram-project"></i></span>\n'
'                    <span class="text-xs font-semibold text-violet-700">构建流水线</span>\n'
'                    <span class="text-[10px] text-violet-400 hidden sm:inline">可插拔构建步骤</span>\n'
'                </div>\n'
'                <div class="p-3">\n'
'                    <div class="flex gap-1 bg-slate-100 rounded-lg p-1 mb-2" id="pipelineTabs">\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-[11px] font-medium transition bg-white text-slate-700 shadow-sm" data-ptab="config_export" onclick="switchPipelineTab(\'config_export\')">1.配置导出</button>\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-[11px] font-medium transition text-slate-500" data-ptab="resource_build" onclick="switchPipelineTab(\'resource_build\')">2.资源打包</button>\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-[11px] font-medium transition text-slate-500" data-ptab="hot_release" onclick="switchPipelineTab(\'hot_release\')">3.热更发布</button>\n'
'                        <button class="flex-1 py-1.5 px-2 rounded text-[11px] font-medium transition text-slate-500" data-ptab="apk_build" onclick="switchPipelineTab(\'apk_build\')">4.APK打包</button>\n'
'                    </div>\n'

# Tab panels
'                    <div id="ptabConfigExport" class="pipeline-panel" style="margin:0;">\n'
'                        <label class="flex items-center gap-1.5 mb-1"><input type="checkbox" id="ppConfigExport" checked style="accent-color:#6366f1;" onchange="togglePipelineStepUI(\'config_export\')"><span class="text-xs font-medium text-slate-700">配置导出发布</span><span class="text-[10px] text-slate-400">— ConfigRemotePublish</span></label>\n'
'                        <div id="ppConfigExportBody" style="display:grid;grid-template-columns:1fr 1fr auto;gap:8px;background:#f8fafc;padding:10px;border-radius:8px;">\n'
'                            <div><span class="text-[10px] text-slate-400">远端路径前缀 <span class="text-rose-400">*</span></span><input id="ppCfgPrefix" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" value="config-release"></div>\n'
'                            <div><span class="text-[10px] text-slate-400">客户端版本</span><input id="ppCfgClientVer" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" value="1.0.0"></div>\n'
'                            <div style="align-self:end;padding-bottom:4px;"><label class="flex items-center gap-1 text-xs"><input type="checkbox" id="ppCfgIncludeCode"> 含代码</label></div>\n'
'                        </div>\n'
'                    </div>\n'

'                    <div id="ptabResourceBuild" class="pipeline-panel hidden" style="margin:0;">\n'
'                        <label class="flex items-center gap-1.5 mb-1"><input type="checkbox" id="ppResourceBuild" checked style="accent-color:#6366f1;" onchange="togglePipelineStepUI(\'resource_build\')"><span class="text-xs font-medium text-slate-700">资源打包</span><span class="text-[10px] text-slate-400">— ResourcePipelineWorkbench</span></label>\n'
'                        <div id="ppResourceBuildBody" style="display:grid;grid-template-columns:1fr 1fr;gap:8px;background:#f8fafc;padding:10px;border-radius:8px;">\n'
'                            <div><span class="text-[10px] text-slate-400">构建引擎 <span class="text-rose-400">*</span></span><select id="ppResProvider" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option value="addressables-v2">Addressables v2（推荐）</option><option value="legacy-bundle-builder">Legacy</option></select></div>\n'
'                            <div><span class="text-[10px] text-slate-400">场景方案</span><input id="ppResScenario" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" value="default"></div>\n'
'                        </div>\n'
'                    </div>\n'

'                    <div id="ptabHotRelease" class="pipeline-panel hidden" style="margin:0;">\n'
'                        <label class="flex items-center gap-1.5 mb-1"><input type="checkbox" id="ppHotRelease" checked style="accent-color:#6366f1;" onchange="togglePipelineStepUI(\'hot_release\')"><span class="text-xs font-medium text-slate-700">代码+资源热更发布</span><span class="text-[10px] text-slate-400">— CommercialReleaseCli</span></label>\n'
'                        <div id="ppHotReleaseBody" style="background:#f8fafc;padding:10px;border-radius:8px;">\n'
'                            <div style="display:flex;flex-wrap:wrap;align-items:center;gap:8px;margin-bottom:8px;">\n'
'                                <span class="text-[11px] text-slate-500">发布对象<span class="text-rose-400">*</span>:</span>\n'
'                                <span id="ppChipCode" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-blue-100 text-blue-700 border-2 border-blue-300 cursor-pointer select-none" onclick="togglePpChip(\'code\')"><i class="fas fa-code text-[9px]"></i>代码包</span>\n'
'                                <span id="ppChipResource" class="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-emerald-100 text-emerald-700 border-2 border-emerald-300 cursor-pointer select-none" onclick="togglePpChip(\'resource\')"><i class="fas fa-cube text-[9px]"></i>资源包</span>\n'
'                            </div>\n'
'                            <div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px;margin-bottom:8px;">\n'
'                                <div><span class="text-[10px] text-slate-400">渠道<span class="text-rose-400">*</span></span><select id="ppHrChannel" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option>common</option><option>official</option><option>tap</option><option>bilibili</option></select></div>\n'
'                                <div><span class="text-[10px] text-slate-400">热更标签</span><input id="ppHrLabels" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" value="hotupdate,aotmeta"></div>\n'
'                                <div><span class="text-[10px] text-slate-400">发布模式<span class="text-rose-400">*</span></span><select id="ppHrMode" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white" onchange="onPpHrModeChange()"><option value="build-upload">构建并上传</option><option value="build">仅构建</option><option value="upload">仅上传</option><option value="activate">激活</option><option value="rollback">回滚</option></select></div>\n'
'                                <div><span class="text-[10px] text-slate-400">上传模式</span><select id="ppHrUpload" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs bg-white"><option value="incremental">增量</option><option value="full">全量</option></select></div>\n'
'                                <div id="ppHrRollbackWrap"><span class="text-[10px] text-slate-400">回滚目标</span><input id="ppHrRollback" class="w-full px-1.5 py-1 border border-slate-200 rounded text-xs" placeholder="回滚模式填写" disabled></div>\n'
'                            </div>\n'
'                            <div style="display:grid;grid-template-columns:1fr 1fr;gap:6px;">\n'
'                                <div style="background:#eff6ff;border:1px solid #bfdbfe;border-radius:8px;padding:8px;">\n'
'                                    <p class="text-[10px] font-semibold text-blue-600 mb-1"><i class="fas fa-code mr-1"></i>代码包策略</p>\n'
'                                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;">\n'
'                                        <div><span class="text-[9px] text-slate-400">启用</span><input type="checkbox" id="ppHrCodeEnabled" checked></div>\n'
'                                        <div><span class="text-[9px] text-slate-400">压缩</span><select id="ppHrCodeComp" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option>Zip</option><option>None</option><option>Lz4</option></select></div>\n'
'                                        <div><span class="text-[9px] text-slate-400">加密</span><select id="ppHrCodeEnc" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option>Aes</option><option>None</option><option>Xor</option></select></div>\n'
'                                        <div><span class="text-[9px] text-slate-400">签名</span><select id="ppHrCodeSig" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option value="builtin-signature">启用</option><option value="">关闭</option></select></div>\n'
'                                        <div style="grid-column:1/-1;"><span class="text-[9px] text-slate-400">包单元</span><input id="ppHrCodeUnits" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px]" value="aotmeta, hotupdate, scriptpatch, symbols"></div>\n'
'                                    </div>\n'
'                                </div>\n'
'                                <div style="background:#ecfdf5;border:1px solid #a7f3d0;border-radius:8px;padding:8px;">\n'
'                                    <p class="text-[10px] font-semibold text-emerald-600 mb-1"><i class="fas fa-cube mr-1"></i>资源包策略</p>\n'
'                                    <div style="display:grid;grid-template-columns:1fr 1fr;gap:4px;">\n'
'                                        <div><span class="text-[9px] text-slate-400">启用</span><input type="checkbox" id="ppHrResEnabled" checked></div>\n'
'                                        <div><span class="text-[9px] text-slate-400">压缩</span><select id="ppHrResComp" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option>None</option><option>Zip</option><option>Lz4</option></select></div>\n'
'                                        <div><span class="text-[9px] text-slate-400">加密</span><select id="ppHrResEnc" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option>None</option><option>Aes</option></select></div>\n'
'                                        <div><span class="text-[9px] text-slate-400">签名</span><select id="ppHrResSig" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option value="builtin-signature">启用</option><option value="">关闭</option></select></div>\n'
'                                        <div style="grid-column:1/-1;"><span class="text-[9px] text-slate-400">包单元</span><input id="ppHrResUnits" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px]" value="addressable, hotupdate, optional, platform, hd, streaming"></div>\n'
'                                    </div>\n'
'                                </div>\n'
'                            </div>\n'
'                            <details style="margin-top:6px;"><summary class="cursor-pointer text-[10px] text-slate-400">高级覆盖</summary><div style="display:grid;grid-template-columns:1fr 1fr 1fr;gap:4px;margin-top:4px;"><div><span class="text-[9px] text-slate-400">压缩覆盖</span><select id="ppHrCompOvr" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option value="">默认</option><option>Zip</option><option>Lz4</option><option>None</option></select></div><div><span class="text-[9px] text-slate-400">加密覆盖</span><select id="ppHrEncOvr" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option value="">默认</option><option>Aes</option><option>Xor</option><option>None</option></select></div><div><span class="text-[9px] text-slate-400">签名覆盖</span><select id="ppHrSigOvr" class="w-full px-1 py-0.5 border border-slate-200 rounded text-[9px] bg-white"><option value="">默认</option><option value="builtin-signature">启用</option></select></div></div></details>\n'
'                        </div>\n'
'                    </div>\n'

'                    <div id="ptabApkBuild" class="pipeline-panel hidden" style="margin:0;">\n'
'                        <label class="flex items-center gap-1.5 mb-1"><input type="checkbox" id="ppApkBuild" style="accent-color:#6366f1;" onchange="togglePipelineStepUI(\'apk_build\')"><span class="text-xs font-medium text-slate-700">APK 打包上传</span><span class="text-[10px] text-slate-400">— Unity BuildPipeline</span></label>\n'
'                        <div id="ppApkBuildBody" class="hidden" style="background:#f8fafc;padding:10px;border-radius:8px;"><p class="text-[11px] text-slate-400">APK参数已在上方配置，此处仅控制是否执行。</p></div>\n'
'                    </div>\n'
'                </div>\n'
'            </div>\n'
'        </div>\n'
'        <div class="px-4 py-2 border-t border-slate-100 bg-slate-50 flex justify-end gap-2 shrink-0">\n'
'            <button type="button" onclick="closeVersionModal()" class="px-3 py-1.5 border border-slate-200 rounded-lg text-xs text-slate-700 hover:bg-slate-100">取消</button>\n'
'            <button type="button" onclick="saveVersion()" class="px-4 py-1.5 bg-indigo-600 text-white rounded-lg text-xs font-medium hover:bg-indigo-700 shadow-sm">保存版本</button>\n'
'        </div>\n'
'    </div>\n'
'</div>\n'
)

idx_start = content.find(old_start)
idx_end = content.find(old_end, idx_start)
if idx_start >= 0 and idx_end > 0:
    content = content[:idx_start] + new_modal + content[idx_end:]
    print('V3 modal replaced successfully')
else:
    print('Markers not found')

with open('routes/admin_routes.py', 'w', encoding='utf-8') as f:
    f.write(content)
print('Done')
