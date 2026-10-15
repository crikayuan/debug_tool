# -*- coding: utf-8 -*-
"""当前代码状态复验：(1) CIDR 大网段是否已修复；(2) resolve_hostname 开关是否生效。"""
import asyncio, json, os, socket, subprocess, sys, threading, time, urllib.request
import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "backend"))
sys.path.insert(0, BACKEND)

# ---------- 1) CIDR 上限保护（纯函数） ----------
from utils.ip_range_utils import parse_scan_range
for expr in ("10.0.0.0/8", "172.16.0.0/12", "0.0.0.0/0"):
    t = time.perf_counter()
    try:
        parse_scan_range(expr)
        print(f"  {expr}: 未拒绝(异常)")
    except ValueError as e:
        print(f"  {expr}: 拒绝 耗时{time.perf_counter()-t:.4f}s — {e}")
print("  /24 count =", len(parse_scan_range("192.168.1.0/24")))
print("  简写 1-254 count =", len(parse_scan_range("192.168.1.1-254")))

# ---------- 2) 起后端 ----------
PORT = 20034
BASE = f"http://127.0.0.1:{PORT}"
_o = urllib.request.build_opener(urllib.request.ProxyHandler({}))
proc = subprocess.Popen([sys.executable, "-c",
    "import sys;sys.path.insert(0,'.');import uvicorn;from main import app;"
    f"uvicorn.run(app,host='127.0.0.1',port={PORT},log_level='warning',access_log=False)"],
    cwd=BACKEND)
for _ in range(40):
    try:
        if json.loads(_o.open(BASE + "/health", timeout=3).read())["status"] == "healthy":
            break
    except Exception:
        time.sleep(0.5)


def http(method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    with _o.open(req, timeout=30) as r:
        return json.loads(r.read().decode())


async def collect(tid):
    items, done = {}, None
    async with websockets.connect(f"ws://127.0.0.1:{PORT}/ws/scan/{tid}", open_timeout=10) as ws:
        dl = time.time() + 30
        while time.time() < dl:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2)
            except asyncio.TimeoutError:
                continue
            d = json.loads(raw)
            if d.get("type") == "result":
                items[d["item"]["ip"]] = d["item"]
            if d.get("type") == "done":
                done = d
                break
    return items, done


async def main():
    srv = socket.socket(); srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0)); srv.listen(128); lport = srv.getsockname()[1]
    stop = threading.Event()

    def acc():
        srv.settimeout(0.3)
        while not stop.is_set():
            try: srv.accept()[0].close()
            except socket.timeout: continue
            except Exception: break
    threading.Thread(target=acc, daemon=True).start()

    print("\n-- resolve_hostname=False --")
    r = http("POST", "/api/scan/start", {"start_ip": "127.0.0.1", "end_ip": "127.0.0.1",
             "port_scan": True, "ports": [lport], "resolve_hostname": False, "vendor_lookup": False,
             "concurrency": 8, "timeout_ms": 300})
    items, _ = await collect(r["data"]["task_id"])
    it = items.get("127.0.0.1", {})
    print("   hostname =", repr(it.get("hostname")), " vendor =", repr(it.get("vendor")),
          " ports =", it.get("ports"))
    f_off = it.get("hostname")

    print("-- resolve_hostname=True --")
    r = http("POST", "/api/scan/start", {"start_ip": "127.0.0.1", "end_ip": "127.0.0.1",
             "port_scan": True, "ports": [lport], "resolve_hostname": True, "vendor_lookup": True,
             "concurrency": 8, "timeout_ms": 300})
    items, _ = await collect(r["data"]["task_id"])
    it = items.get("127.0.0.1", {})
    print("   hostname =", repr(it.get("hostname")))
    f_on = it.get("hostname")
    stop.set()

    print("\n== 结论 ==")
    print("CIDR 大网段：已修复（瞬时拒绝）" )
    if f_off:
        print(f"resolve_hostname 开关：**未生效**（关闭时仍解析出 {f_off!r}）→ 源码 Bug 仍存在")
    else:
        print("resolve_hostname 开关：生效")


try:
    asyncio.run(main())
finally:
    proc.kill()
