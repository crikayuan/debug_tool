# -*- coding: utf-8 -*-
"""打包版（20001）网络扫描链路验证。"""
import asyncio, json, os, sys, time, urllib.request
import websockets

BASE = "http://127.0.0.1:20001"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "_out")
os.makedirs(OUT, exist_ok=True)
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
PASS, FAIL = [], []


def check(n, c, d=""):
    (PASS if c else FAIL).append(n)
    print(f"  [{'PASS' if c else 'FAIL'}] {n}" + (f" — {d}" if d else ""))


def http(method, path, body=None, timeout=40):
    data = json.dumps(body).encode() if body is not None else None
    h = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=h, method=method)
    with _opener.open(req, timeout=timeout) as r:
        return r.status, json.loads(r.read().decode())


async def collect(tid, timeout=90):
    frames, dl = [], time.time() + timeout
    async with websockets.connect(f"ws://127.0.0.1:20001/ws/scan/{tid}", open_timeout=10) as ws:
        while time.time() < dl:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
            except asyncio.TimeoutError:
                continue
            d = json.loads(raw); frames.append(d)
            if d.get("type") == "done":
                break
    return frames


async def main():
    print("== 打包版扫描链路 ==")
    st, r = http("POST", "/api/scan/start", {"start_ip": "192.168.1.1", "end_ip": "192.168.1.80",
                 "port_scan": False, "resolve_hostname": False, "concurrency": 64, "timeout_ms": 300})
    check("start 200", st == 200 and r["data"]["task_id"], str(r.get("data")))
    tid = r["data"]["task_id"]
    frames = await collect(tid)
    done = [f for f in frames if f.get("type") == "done"]
    check("收到 done", len(done) == 1, str(done[-1] if done else None))
    items = {}
    for f in frames:
        if f.get("type") == "result" and f.get("item"):
            items[f["item"]["ip"]] = f["item"]
    check("有扫描结果", len(items) > 0, f"n={len(items)}")

    # 打包版 OUI 是否生效：任一设备的 vendor 非空即证明内置 oui.txt 可用
    with_vendor = [(ip, it["vendor"]) for ip, it in items.items() if it.get("vendor")]
    check("打包版厂商识别可用（内置 oui.txt）", len(with_vendor) > 0, str(with_vendor[:3]))

    st, r = http("GET", f"/api/scan/result/{tid}")
    check("result 200", st == 200 and "items" in (r.get("data") or {}), f"st={st}")

    st, r = http("POST", "/api/scan/export", {
        "items": [{"ip": i["ip"], "mac": i["mac"], "vendor": i["vendor"], "hostname": i["hostname"],
                   "delay_ms": i["delay_ms"], "ports": i["ports"], "online": i["online"], "note": ""}
                  for i in items.values()],
        "directory": OUT, "filename": "qa_pack_export.csv"})
    p = (r.get("data") or {}).get("path", "")
    check("打包版导出 CSV", st == 200 and os.path.exists(p), f"st={st} path={p}")
    if os.path.exists(p):
        with open(p, "rb") as f:
            check("导出带 BOM", f.read(3) == b"\xef\xbb\xbf")

    print(f"\n  汇总 PASS {len(PASS)}/{len(PASS)+len(FAIL)}")
    for f in FAIL:
        print("   FAIL:", f)
    return 1 if FAIL else 0


sys.exit(asyncio.run(main()))
