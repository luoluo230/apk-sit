#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""飞书 bot v2 发送文本消息，避免 9499 Bad Request（使用 msg_type=text）"""
import sys
import json
import urllib.request

def main():
    if len(sys.argv) < 2:
        print("Usage: feishu_send.py WEBHOOK_URL < message.txt")
        sys.exit(0)
    webhook = sys.argv[1]
    text = sys.stdin.read().strip()
    if not text:
        print("No message body")
        sys.exit(0)
    data = json.dumps({"msg_type": "text", "content": {"text": text}}, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(webhook, data=data, method="POST", headers={"Content-Type": "application/json; charset=utf-8"})
    try:
        r = urllib.request.urlopen(req, timeout=10)
        if r.getcode() == 200:
            print("✅ 通知已发送")
        else:
            print("⚠️ 飞书返回状态:", r.getcode())
    except Exception as e:
        print("❌ 飞书通知发送失败:", e)
    sys.exit(0)

if __name__ == "__main__":
    main()
