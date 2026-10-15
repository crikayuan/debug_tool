# -*- coding: utf-8 -*-
"""QA 焦点复测：开关语义（resolve_hostname / vendor_lookup / port_scan）、停止保留、明细。"""
import asyncio
import json
import os
import socket
import sys
import threading
import time
import urllib.error
import urllib.request

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.normpath(os.path.join(HERE, "..", "backend")))
BASE = "http://127.0.0.1:20033"
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def http(method, path, body=None, timeout=40):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with _opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode())
        except Exception:
            return e.code, {}


async def collect(task_id, timeout=60):
    frames = []
    dl = time.time() + timeout
    try:
        async with websockets.connect(f"ws://127.0.0.1:20033/ws/scan/{task_id}", open_timeout=10) as ws:
            while time.time() < dl:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                frames.append(d)
                if d.get("type") == "done":
                    break
    except Exception as e:
        frames.append({"_err": str(e)})
    return frames


def last_items(frames):
    m = {}
    for f in frames:
        if f.get("type") == "result" and f.get("item"):
            m[f["item"]["ip"]] = f["item"]
    return m


async def main():
    # 本地监听端口（用于让 127.0.0.1 快速判活）
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(128); lport = srv.getsockname()[1]
    stop_srv = threading.Event()

    def acc():
        srv.settimeout(0.3)
        while not stop_srv.is_set():
            try: srv.accept()[0].close()
            except socket.timeout: continue
            except Exception: break
    threading.Thread(target=acc, daemon=True).start()

    print("== A. resolve_hostname 开关语义 ==")
    st, r = http("POST", "/api/scan/start", {"start_ip": "127.0.0.1", "end_ip": "127.0.0.1",
                 "port_scan": True, "ports": [lport], "resolve_hostname": False,
                 "vendor_lookup": False, "concurrency": 8, "timeout_ms": 300})
    t = r["data"]["task_id"]
    items = last_items(await collect(t))
    it = items.get("127.0.0.1", {})
    check("resolve_hostname=False 时主机名应为空",
          it.get("hostname", "") == "", f"实际 hostname={it.get('hostname')!r}")
    check("vendor_lookup=False 时厂商应为空", it.get("vendor", "") == "", f"实际 vendor={it.get('vendor')!r}")

    print("\n== B. resolve_hostname=True 对照 ==")
    st, r = http("POST", "/api/scan/start", {"start_ip": "127.0.0.1", "end_ip": "127.0.0.1",
                 "port_scan": True, "ports": [lport], "resolve_hostname": True,
                 "vendor_lookup": True, "concurrency": 8, "timeout_ms": 300})
    t = r["data"]["task_id"]
    items = last_items(await collect(t))
    it = items.get("127.0.0.1", {})
    check("resolve_hostname=True 时主机名非空", bool(it.get("hostname")), f"hostname={it.get('hostname')!r}")

    print("\n== C. 停止：确定性保留已扫结果 ==")
    # 127.0.0.1 会很快判活；127.0.0.2~100 会慢（超时），确保停止时已有完成项
    st, r = http("POST", "/api/scan/start", {"start_ip": "127.0.0.1", "end_ip": "127.0.0.100",
                 "port_scan": True, "ports": [lport], "resolve_hostname": False,
                 "vendor_lookup": False, "concurrency": 4, "timeout_ms": 300})
    t = r["data"]["task_id"]
    await asyncio.sleep(1.2)
    http("POST", f"/api/scan/stop/{t}")
    await asyncio.sleep(1.0)
    d = http("GET", f"/api/scan/result/{t}")[1].get("data") or {}
    check("停止后 status=stopped", d.get("status") == "stopped", f"status={d.get('status')}")
    check("停止时已扫描数 >0", (d.get("scanned") or 0) > 0, f"scanned={d.get('scanned')}")
    ips = [i["ip"] for i in d.get("items", [])]
    check("已扫到的 127.0.0.1 结果被保留", "127.0.0.1" in ips, f"items={ips}")

    print("\n== D. port_scan=False 时端口列应为空 ==")
    st, r = http("POST", "/api/scan/start", {"start_ip": "127.0.0.1", "end_ip": "127.0.0.1",
                 "port_scan": False, "ports": [lport], "resolve_hostname": False,
                 "concurrency": 8, "timeout_ms": 300})
    t = r["data"]["task_id"]
    items = last_items(await collect(t))
    it = items.get("127.0.0.1", {})
    check("port_scan=False -> ports 为空", it.get("ports") == [], f"ports={it.get('ports')} online={it.get('online')}")

    stop_srv.set()

    print("\n== E. 本网段明细（本机 / 离线项）==")
    st, r = http("POST", "/api/scan/start", {"start_ip": "192.168.1.1", "end_ip": "192.168.1.160",
                 "port_scan": False, "resolve_hostname": False, "concurrency": 64, "timeout_ms": 300})
    t = r["data"]["task_id"]
    await collect(t, timeout=120)
    d = http("GET", f"/api/scan/result/{t}")[1].get("data") or {}
    for i in d.get("items", []):
        print(f"       {i['ip']:<16} online={str(i['online']):<5} mac={i['mac']:<17} vendor={i.get('vendor','')[:28]!r} ports={i['ports']}")
    self_it = next((i for i in d["items"] if i["ip"] == "192.168.1.153"), None)
    check("本机 192.168.1.153 在结果中", self_it is not None, str(self_it))

    print("\n===== 汇总 =====")
    print(f"  PASS {len(PASS)} / {len(PASS)+len(FAIL)}")
    for f in FAIL:
        print("   FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
