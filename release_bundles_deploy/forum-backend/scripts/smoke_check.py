#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""基础 smoke check。"""

import sys
import urllib.request
import urllib.error


def fetch(url):
    req = urllib.request.Request(url, headers={'User-Agent': 'apk-site-smoke/1.0'})
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode('utf-8', errors='ignore')
        return resp.status, body


def main(argv=None):
    argv = argv or sys.argv[1:]
    base = (argv[0] if argv else 'http://127.0.0.1:5003').rstrip('/')
    checks = [
        ('health', '/health'),
        ('status', '/api/status'),
        ('home', '/'),
        ('docs', '/api/docs'),
    ]
    failed = []
    for label, path in checks:
        try:
            status, _ = fetch(base + path)
            print('%s %s' % (label, status))
            if status != 200:
                failed.append(label)
        except urllib.error.HTTPError as exc:
            print('%s HTTP %s' % (label, exc.code))
            failed.append(label)
        except Exception as exc:
            print('%s ERROR %s' % (label, exc))
            failed.append(label)
    return 1 if failed else 0


if __name__ == '__main__':
    sys.exit(main())
