#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import argparse
import os

os.environ.setdefault("APP_PORTAL_MODE", "forum")
os.environ.setdefault("APK_PORT", os.getenv("FORUM_PORT", "5005"))
os.environ.setdefault("ENABLE_DOWNLOAD_FILE_SERVICE", "false")
os.environ.setdefault("ENABLE_BACKGROUND_SCHEDULER", "false")

from app_new import app  # noqa: E402


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=int(os.getenv("APK_PORT", "5005")))
    args = parser.parse_args()
    os.environ["APK_PORT"] = str(args.port)
    app.run(host=os.getenv("APK_HOST", "0.0.0.0"), port=args.port, debug=False)
