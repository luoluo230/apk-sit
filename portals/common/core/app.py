#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""DEPRECATED: 旧入口，已禁用。请使用 app_new + *_wsgi 入口。"""

MESSAGE = (
    "[DEPRECATED ENTRY] app.py 已禁用。\n"
    "请使用以下唯一入口启动：\n"
    "  - Admin : waitress admin_wsgi:app\n"
    "  - Player: waitress player_wsgi:app\n"
    "  - Forum : waitress forum_wsgi:app\n"
)

if __name__ == '__main__':
    print(MESSAGE)
    raise SystemExit(2)
