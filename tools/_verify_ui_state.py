import re, time, requests
s = requests.Session()
r = s.get("http://127.0.0.1:5003/login", timeout=15)
m = re.search(r'name="csrf_token"[^>]*value="([^"]+)"', r.text or "")
s.post("http://127.0.0.1:5003/login", data={"username": "admin", "password": "admin123", "csrf_token": m.group(1) if m else ""}, timeout=15)
for i in range(3):
    d = s.get("http://127.0.0.1:5003/api/ops-platform/agent/detail?project_id=GomeKu&agent_id=agent-local-cn-1", timeout=30).json()
    for svc in (d.get("agent") or {}).get("services") or []:
        sid = str(svc.get("service_id") or "")
        if sid in ("mongo-db-cn-1", "redis-cache-cn-1"):
            print(f"round{i+1}", sid, svc.get("status"), svc.get("probe_status"), svc.get("updated_at"))
    time.sleep(8)
