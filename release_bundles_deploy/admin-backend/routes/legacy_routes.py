# -*- coding: utf-8 -*-
"""
占位路由：管理中心、数据分析、构建管理、版本管理尚未迁移到独立 Blueprint 时，
在此注册占位路由，避免 404。后续可将完整实现迁入 routes/admin、dashboard、build、versions。
"""

from flask import redirect
from flask import render_template_string

ADMIN_PANEL_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>管理中心 - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
    <link rel="stylesheet" href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.0.0/css/all.min.css">
</head>
<body class="bg-gray-50 min-h-screen">
    <div class="container mx-auto px-4 py-8">
        <div class="flex justify-between items-center mb-8">
            <h1 class="text-2xl font-bold text-gray-800">管理中心</h1>
            <a href="/" class="text-blue-600 hover:underline">← 返回首页</a>
        </div>
        <div class="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-6">
            <a href="/admin/users" class="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
                <div class="flex items-center">
                    <i class="fas fa-users text-blue-500 text-2xl mr-4"></i>
                    <div>
                        <h2 class="text-lg font-semibold text-gray-800">用户管理</h2>
                        <p class="text-sm text-gray-500">管理系统用户与权限</p>
                    </div>
                </div>
            </a>
            <a href="/admin/projects" class="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
                <div class="flex items-center">
                    <i class="fas fa-folder text-green-500 text-2xl mr-4"></i>
                    <div>
                        <h2 class="text-lg font-semibold text-gray-800">项目管理</h2>
                        <p class="text-sm text-gray-500">APK 项目分组与配置</p>
                    </div>
                </div>
            </a>
            <a href="/admin/build" class="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
                <div class="flex items-center">
                    <i class="fas fa-cog text-orange-500 text-2xl mr-4"></i>
                    <div>
                        <h2 class="text-lg font-semibold text-gray-800">构建管理</h2>
                        <p class="text-sm text-gray-500">Jenkins 构建与日志</p>
                    </div>
                </div>
            </a>
            <a href="/dashboard" class="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
                <div class="flex items-center">
                    <i class="fas fa-chart-pie text-purple-500 text-2xl mr-4"></i>
                    <div>
                        <h2 class="text-lg font-semibold text-gray-800">数据分析</h2>
                        <p class="text-sm text-gray-500">下载统计与报表</p>
                    </div>
                </div>
            </a>
            <a href="/admin/versions" class="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
                <div class="flex items-center">
                    <i class="fas fa-code-branch text-teal-500 text-2xl mr-4"></i>
                    <div>
                        <h2 class="text-lg font-semibold text-gray-800">版本管理</h2>
                        <p class="text-sm text-gray-500">APK 版本与更新说明</p>
                    </div>
                </div>
            </a>
            <a href="/admin/audit-log" class="block p-6 bg-white rounded-lg shadow hover:shadow-md transition">
                <div class="flex items-center">
                    <i class="fas fa-history text-gray-500 text-2xl mr-4"></i>
                    <div>
                        <h2 class="text-lg font-semibold text-gray-800">操作日志</h2>
                        <p class="text-sm text-gray-500">审计与操作记录</p>
                    </div>
                </div>
            </a>
        </div>
    </div>
</body>
</html>
'''

STUB_PAGE_HTML = '''<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ title }} - APK 下载中心</title>
    <link rel="stylesheet" href="/static/tailwind.css">
</head>
<body class="bg-gray-50 min-h-screen flex items-center justify-center">
    <div class="bg-white rounded-lg shadow p-8 max-w-md text-center">
        <p class="text-gray-600 mb-4">{{ message }}</p>
        <a href="/admin" class="text-blue-600 hover:underline">← 返回管理中心</a>
    </div>
</body>
</html>
'''


def register(app):
    login_required = app.login_required
    admin_required = app.admin_required

    @app.route('/admin')
    @admin_required
    def admin_panel():
        return render_template_string(ADMIN_PANEL_HTML)

    @app.route('/admin/users')
    @admin_required
    def admin_users_stub():
        return render_template_string(
            STUB_PAGE_HTML,
            title='用户管理',
            message='用户管理功能迁移中，请稍后。'
        )

    @app.route('/admin/projects')
    @admin_required
    def admin_projects_stub():
        return render_template_string(
            STUB_PAGE_HTML,
            title='项目管理',
            message='项目管理功能迁移中，请稍后。'
        )

    @app.route('/admin/audit-log')
    @admin_required
    def admin_audit_log_stub():
        return render_template_string(
            STUB_PAGE_HTML,
            title='操作日志',
            message='操作日志功能迁移中，请稍后。'
        )

    @app.route('/admin/versions')
    @admin_required
    def admin_versions_stub():
        return render_template_string(
            STUB_PAGE_HTML,
            title='版本管理',
            message='版本管理功能迁移中，请稍后。'
        )

    @app.route('/dashboard')
    @login_required
    def dashboard_stub():
        return render_template_string(
            STUB_PAGE_HTML,
            title='数据分析',
            message='数据分析功能迁移中，请稍后。'
        )

    @app.route('/admin/build')
    @admin_required
    def build_stub():
        return render_template_string(
            STUB_PAGE_HTML,
            title='构建管理',
            message='构建管理功能迁移中，请稍后。'
        )
