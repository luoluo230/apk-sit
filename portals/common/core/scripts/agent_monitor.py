# -*- coding: utf-8 -*-
"""
MA Agent Monitor — 每个节点一个独立黑窗口
实时显示该节点的端口监听、连接状态、指标数据
"""
import sys
import os
import time
import socket
import json
import threading
import subprocess
from datetime import datetime

# 配置
AGENT_ID = sys.argv[1] if len(sys.argv) > 1 else "unknown"
PROBE_HOST = sys.argv[2] if len(sys.argv) > 2 else "127.0.0.1"
PROBE_PORT = int(sys.argv[3]) if len(sys.argv) > 3 else 0
OPS_URL = sys.argv[4] if len(sys.argv) > 4 else ""
OPS_KEY = sys.argv[5] if len(sys.argv) > 5 else ""
REFRESH_SEC = 2

# 颜色
class C:
    RESET = "\033[0m"
    BOLD = "\033[1m"
    RED = "\033[91m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    CYAN = "\033[96m"
    WHITE = "\033[97m"
    DIM = "\033[2m"

def cls():
    os.system("cls" if os.name == "nt" else "clear")

def tcp_check(host, port, timeout=2):
    """TCP 连接检测"""
    if not port:
        return False, 0.0
    try:
        t0 = time.monotonic()
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.settimeout(timeout)
        s.connect((host, port))
        rtt = (time.monotonic() - t0) * 1000
        s.close()
        return True, rtt
    except Exception:
        return False, 0.0

def fetch_ops_health(ops_url, ops_key):
    """调用 /ops/health 获取指标"""
    if not ops_url:
        return None
    try:
        import urllib.request
        url = f"{ops_url}/ops/health"
        req = urllib.request.Request(url)
        if ops_key:
            req.add_header("X-Ops-Key", ops_key)
            req.add_header("X-Ops-Actor", "agent-monitor")
            req.add_header("X-Ops-Role", "SuperAdmin")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def fetch_ops_cluster(ops_url, ops_key):
    """调用 /ops/cluster 获取集群状态"""
    if not ops_url:
        return None
    try:
        import urllib.request
        url = f"{ops_url}/ops/cluster"
        req = urllib.request.Request(url)
        if ops_key:
            req.add_header("X-Ops-Key", ops_key)
            req.add_header("X-Ops-Actor", "agent-monitor")
            req.add_header("X-Ops-Role", "SuperAdmin")
            req.add_header("X-Ops-Reason", "agent-monitor")
            req.add_header("X-Ops-TicketId", "MONITOR")
        with urllib.request.urlopen(req, timeout=3) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except Exception:
        return None

def get_connections(port):
    """获取连接到指定端口的 ESTABLISHED 连接数"""
    try:
        result = subprocess.run(
            ["netstat", "-ano"],
            capture_output=True, text=True, timeout=5
        )
        count = 0
        for line in result.stdout.splitlines():
            parts = line.strip().split()
            if len(parts) >= 4 and parts[3] == "ESTABLISHED":
                # 检查本地端口是否匹配
                local_addr = parts[1]
                if f":{port}" in local_addr:
                    count += 1
        return count
    except Exception:
        return -1

def get_psutil_metrics():
    """采集本机 CPU/内存"""
    try:
        import psutil
        return {
            "cpu": round(psutil.cpu_percent(interval=0.1), 1),
            "mem": round(psutil.virtual_memory().percent, 1),
            "mem_used_gb": round(psutil.virtual_memory().used / 1024**3, 1),
            "mem_total_gb": round(psutil.virtual_memory().total / 1024**3, 1),
        }
    except ImportError:
        return None

def render(history):
    cls()
    now = datetime.now().strftime("%H:%M:%S")

    # 标题
    print(f"{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}  AGENT: {AGENT_ID}{C.RESET}")
    print(f"{C.DIM}  刷新于 {now} | 间隔 {REFRESH_SEC}s{C.RESET}")
    print(f"{C.BOLD}{C.CYAN}{'='*60}{C.RESET}")

    # 端口检测
    ok, rtt = tcp_check(PROBE_HOST, PROBE_PORT)
    status_str = f"{C.GREEN}● ONLINE{C.RESET}" if ok else f"{C.RED}● OFFLINE{C.RESET}"
    rtt_str = f"{rtt:.1f}ms" if ok else "-"
    port_str = f"{PROBE_HOST}:{PROBE_PORT}" if PROBE_PORT else "N/A (内部服务)"
    print(f"\n  端口检测: {status_str}")
    print(f"  目标地址: {port_str}")
    print(f"  探活 RTT: {rtt_str}")

    # 连接数
    if PROBE_PORT:
        conns = get_connections(PROBE_PORT)
        conn_str = str(conns) if conns >= 0 else "?"
        print(f"  活跃连接: {conn_str}")
    else:
        print(f"  活跃连接: N/A")

    # Ops Health 指标
    health = fetch_ops_health(OPS_URL, OPS_KEY)
    if health and health.get("success"):
        data = health.get("data", {})
        tel = data.get("Telemetry", {})
        print(f"\n{C.BOLD}  ── Ops Telemetry ──{C.RESET}")
        qps = tel.get("Qps", 0)
        p99 = tel.get("P99Ms", 0)
        total_req = tel.get("TotalRequests", 0)
        total_resp = tel.get("TotalResponses", 0)
        queue = tel.get("QueueDepth", 0)
        recon_rate = tel.get("ReconnectSuccessRate", 1.0)
        print(f"  QPS:        {C.YELLOW}{qps}{C.RESET}")
        print(f"  P99 RTT:    {C.YELLOW}{p99}ms{C.RESET}")
        print(f"  总请求:     {total_req}")
        print(f"  总响应:     {total_resp}")
        print(f"  队列深度:   {queue}")
        print(f"  重连成功率: {recon_rate*100:.1f}%")
    else:
        print(f"\n  {C.DIM}Ops Telemetry: 不可用{C.RESET}")

    # 本机资源
    pm = get_psutil_metrics()
    if pm:
        print(f"\n{C.BOLD}  ── 本机资源 ──{C.RESET}")
        cpu_color = C.GREEN if pm["cpu"] < 70 else C.YELLOW if pm["cpu"] < 90 else C.RED
        mem_color = C.GREEN if pm["mem"] < 70 else C.YELLOW if pm["mem"] < 90 else C.RED
        print(f"  CPU: {cpu_color}{pm['cpu']}%{C.RESET}")
        print(f"  内存: {mem_color}{pm['mem']}%{C.RESET} ({pm['mem_used_gb']}/{pm['mem_total_gb']} GB)")

    # 历史趋势（最近20条 RTT）
    if len(history) > 1:
        print(f"\n{C.BOLD}  ── RTT 趋势 (最近{min(len(history),20)}次) ──{C.RESET}")
        recent = history[-20:]
        bar = ""
        for h in recent:
            r = h.get("rtt", 0)
            if h.get("ok"):
                if r < 5:
                    bar += f"{C.GREEN}█{C.RESET}"
                elif r < 20:
                    bar += f"{C.YELLOW}█{C.RESET}"
                else:
                    bar += f"{C.RED}█{C.RESET}"
            else:
                bar += f"{C.RED}✗{C.RESET}"
        print(f"  {bar}")
        rtts = [h["rtt"] for h in recent if h.get("ok")]
        if rtts:
            print(f"  min={min(rtts):.1f}ms  max={max(rtts):.1f}ms  avg={sum(rtts)/len(rtts):.1f}ms")

    # 集群节点状态
    cluster = fetch_ops_cluster(OPS_URL, OPS_KEY)
    if cluster and cluster.get("success"):
        servers = cluster.get("data", {}).get("Servers", [])
        print(f"\n{C.BOLD}  ── 集群状态 ({len(servers)} 节点) ──{C.RESET}")
        for srv in servers:
            sid = srv.get("ServerId", "?")
            st = srv.get("State", -1)
            if st == 0:
                st_str = f"{C.GREEN}Online{C.RESET}"
            elif st == 1:
                st_str = f"{C.YELLOW}Maintenance{C.RESET}"
            else:
                st_str = f"{C.RED}Stopped{C.RESET}"
            marker = " ◄" if sid == AGENT_ID else ""
            print(f"  {sid}: {st_str}{marker}")

    print(f"\n{C.DIM}  按 Ctrl+C 退出{C.RESET}")

def main():
    history = []
    print(f"Agent Monitor starting: {AGENT_ID}")
    try:
        while True:
            ok, rtt = tcp_check(PROBE_HOST, PROBE_PORT)
            history.append({"ok": ok, "rtt": rtt, "ts": time.time()})
            if len(history) > 100:
                history = history[-100:]
            render(history)
            time.sleep(REFRESH_SEC)
    except KeyboardInterrupt:
        print(f"\nAgent Monitor stopped: {AGENT_ID}")

if __name__ == "__main__":
    main()
