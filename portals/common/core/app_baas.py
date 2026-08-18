#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Standalone Casual BaaS Portal entrypoint (no topology stack)."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from server_frameworks.casual_baas.standalone_app import create_baas_app

app = create_baas_app()

if __name__ == "__main__":
    port = int(os.getenv("BAAS_PORT") or os.getenv("APP_PORT") or "5004")
    host = os.getenv("BAAS_HOST") or os.getenv("APP_HOST") or "127.0.0.1"
    app.run(host=host, port=port, debug=os.getenv("APK_DEBUG", "").lower() in ("1", "true"))
