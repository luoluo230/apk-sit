#!/bin/zsh
set -euo pipefail
cd /Users/wangling/Desktop/apk-site/portals/intranet
exec /usr/bin/python3 wsgi.py --port 5003
