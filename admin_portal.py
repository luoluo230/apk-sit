#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import argparse

os.environ.setdefault('APP_PORTAL_MODE', 'admin')
os.environ.setdefault('APK_PORT', os.getenv('ADMIN_PORT', os.getenv('APK_PORT', '5003')))

from app_new import app, _on_start  # noqa: E402


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--port', type=int, default=int(os.getenv('APK_PORT', '5003')))
    args = parser.parse_args()
    os.environ['APK_PORT'] = str(args.port)
    _on_start()
    app.run(host=os.getenv('APK_HOST', '0.0.0.0'), port=args.port, debug=False)
