# -*- coding: utf-8 -*-
"""QA 独立集成测试：网络扫描 REST + WS + 持久化（针对已运行的 20033 实例）。

运行： <netassist python> integration_scan.py
"""
import asyncio
import json
import os
import re
import socket
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "backend"))
sys.path.insert(0, BACKEND)

BASE = "http://127.0.0.1:20033"
OUT = os.path.join(HERE, "_out")
os.makedirs(OUT, exist_ok=True)

# 关闭代理，避免 urllib 走系统代理导致 502
_opener = urllib.request.build_opener(urllib.request.ProxyHandler({}))
urllib.request.install_opener(urllib.request.build_opener(urllib.request.ProxyHandler({})))

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def http(method, path, body=None, timeout=30):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(BASE + path, data=data, headers=headers, method=method)
    try:
        with _opener.open(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {}


def ws_url(task_id):
    return f"ws://127.0.0.1:20033/ws/scan/{task_id}"


async def collect_scan(task_id, timeout=60, stop_early=False):
    """连 WS 收集帧，直到 done 或超时。返回 (frames, result_frames_by_ip)"""
    frames = []
    per_ip = {}
    deadline = time.time() + timeout
    try:
        async with websockets.connect(ws_url(task_id), open_timeout=10) as ws:
            while time.time() < deadline:
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=2.0)
                except asyncio.TimeoutError:
                    continue
                try:
                    d = json.loads(raw)
                except Exception:
                    continue
                frames.append(d)
                if d.get("type") == "result" and d.get("item"):
                    ip = d["item"].get("ip")
                    per_ip[ip] = per_ip.get(ip, 0) + 1
                if d.get("type") == "done":
                    break
                if stop_early and d.get("type") == "progress":
                    break
    except Exception as e:
        frames.append({"_ws_error": str(e)})
    return frames, per_ip


def wait_health(timeout=30):
    dl = time.time() + timeout
    while time.time() < dl:
        try:
            st, _ = http("GET", "/health", timeout=3)
            if st == 200:
                return True
        except Exception:
            pass
        time.sleep(0.4)
    return False


def start_task(**cfg):
    st, r = http("POST", "/api/scan/start", cfg)
    return st, r


async def main():
    print("== 0. 健康检查 ==")
    check("后端 20033 就绪", wait_health())

    print("\n== 1. GET /api/scan/segments ==")
    st, r = http("GET", "/api/scan/segments")
    segs = (r.get("data") or {}).get("segments", []) if isinstance(r, dict) else []
    check("segments 200 且非空", st == 200 and len(segs) > 0, f"st={st} n={len(segs)}")
    check("网段字段完整(cidr/ip/type/host_count)",
          all(all(k in s for k in ("cidr", "ip", "type", "host_count")) for s in segs),
          str(segs[:2]))
    check("含本机 192.168.1.0/24 网段", any(s["cidr"] == "192.168.1.0/24" for s in segs),
          str([s["cidr"] for s in segs]))

    print("\n== 2. 非法扫描范围 -> 4xx（不应 500）==")
    bad_cases = [
        ("空范围", {}),
        ("非法串", {"range": "abc"}),
        ("简写越界", {"range": "192.168.1.1-999"}),
        ("起止倒置", {"start_ip": "192.168.1.254", "end_ip": "192.168.1.1"}),
        ("非法CIDR", {"range": "192.168.1.0/33"}),
        ("五段IP", {"range": "1.2.3.4.5"}),
    ]
    for name, cfg in bad_cases:
        st, r = start_task(**cfg)
        check(f"{name} -> 400", st == 400, f"st={st} detail={r.get('detail')}")

    print("\n== 3. 端口探测：本地监听端口应被识别为开放 ==")
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(64)
    lport = srv.getsockname()[1]
    stop_srv = threading.Event()

    def acceptor():
        srv.settimeout(0.3)
        while not stop_srv.is_set():
            try:
                c, _ = srv.accept()
                c.close()
            except socket.timeout:
                continue
            except Exception:
                break
    th = threading.Thread(target=acceptor, daemon=True); th.start()

    st, r = start_task(start_ip="127.0.0.1", end_ip="127.0.0.1", port_scan=True, ports=[lport],
                       resolve_hostname=False, concurrency=8, timeout_ms=300)
    check("开放端口任务启动 200", st == 200 and r.get("data", {}).get("task_id"), str(r))
    tid = r["data"]["task_id"]
    frames, per_ip = await collect_scan(tid, timeout=30)
    done = [f for f in frames if f.get("type") == "done"]
    res = [f["item"] for f in frames if f.get("type") == "result"]
    check("收到 done 帧", len(done) == 1, f"frames={[f.get('type') for f in frames][:8]}")
    check("127.0.0.1 判在线", bool(res) and res[-1]["online"] is True, str(res[-1] if res else None))
    check(f"识别到开放端口 {lport}", bool(res) and res[-1]["ports"] == [lport], str(res[-1] if res else None))

    print("\n== 4. 端口探测：本地关闭端口（本机不回 RST）==")
    st, r = start_task(start_ip="127.0.0.1", end_ip="127.0.0.1", port_scan=True, ports=[59999],
                       resolve_hostname=False, concurrency=8, timeout_ms=300)
    tid2 = r["data"]["task_id"]
    frames2, _ = await collect_scan(tid2, timeout=30)
    res2 = [f["item"] for f in frames2 if f.get("type") == "result"]
    check("关闭端口无结果或判离线（环境: 不回 RST）",
          all(not it.get("online") for it in res2) if res2 else True,
          str(res2))
    stop_srv.set()

    print("\n== 5. 本网段扫描 + ARP 逐条核对 + 本机可扫到 ==")
    st, r = start_task(start_ip="192.168.1.1", end_ip="192.168.1.160", port_scan=False,
                       resolve_hostname=False, concurrency=64, timeout_ms=300)
    check("网段任务启动 200", st == 200, str(r))
    tid3 = r["data"]["task_id"]
    frames3, per_ip3 = await collect_scan(tid3, timeout=120)
    res3 = {f["item"]["ip"]: f["item"] for f in frames3 if f.get("type") == "result"}
    done3 = [f for f in frames3 if f.get("type") == "done"]
    check("网段扫描完成 done", len(done3) == 1, str(done3[-1] if done3 else None))

    from utils.arp_utils import get_arp_table
    arp = get_arp_table()
    arp_in_range = {ip: m for ip, m in arp.items() if ip.startswith("192.168.1.") and 1 <= int(ip.split(".")[-1]) <= 160}

    # 逐条核对：扫描结果里的 MAC 必须与 arp -a 一致
    mism = []
    for ip, it in res3.items():
        if it.get("mac"):
            if ip in arp and arp[ip] != it["mac"]:
                mism.append((ip, it["mac"], arp[ip]))
    check("扫描 MAC 与系统 ARP 表逐条一致", not mism, f"不一致={mism}")

    # ARP 有记录但扫描漏掉的（记录差异，不判失败——TCP 关闭端口在此环境会超时判离线）
    missed = [ip for ip in arp_in_range if ip not in res3]
    covered = [ip for ip in arp_in_range if ip in res3]
    print(f"       ARP 范围设备 {len(arp_in_range)} 台，扫描结果覆盖 {len(covered)}，漏 {len(missed)}: {missed}")
    check("ARP 设备多数被覆盖（>=70%）",
          len(arp_in_range) == 0 or len(covered) >= 0.7 * len(arp_in_range),
          f"{len(covered)}/{len(arp_in_range)}")

    check("本机 IP 192.168.1.153 出现在结果中", "192.168.1.153" in res3,
          f"在线={res3.get('192.168.1.153',{}).get('online')} mac={res3.get('192.168.1.153',{}).get('mac')}")

    # result 帧同一 IP 推两次（TCP 阶段 + enrich 阶段）
    online_ips = [ip for ip, it in res3.items() if it.get("online")]
    twice = [ip for ip in online_ips if per_ip3.get(ip, 0) >= 2]
    check("在线 IP 的 result 帧被推送 >=2 次（TCP+enrich）",
          bool(online_ips) and len(twice) == len(online_ips),
          f"在线={len(online_ips)} 双推={len(twice)} 每IP次数={ {k:per_ip3.get(k) for k in online_ips[:5]} }")

    print("\n== 6. GET /api/scan/result/{task_id} 全量结果 ==")
    st, r = http("GET", f"/api/scan/result/{tid3}")
    data = r.get("data") or {}
    check("result 200 且含 items/status/total",
          st == 200 and "items" in data and data.get("status") == "done",
          f"st={st} status={data.get('status')} items={len(data.get('items', []))}")
    check("result total=160", data.get("total") == 160, f"total={data.get('total')}")
    check("不存在的 task -> 404", http("GET", "/api/scan/result/nonexist")[0] == 404)

    print("\n== 7. 停止扫描：可中断且结果保留 ==")
    # 用真实网段（含开放端口的主机会很快判活），确保停止前已有完成项，避免因首批并发未返回而计 0
    st, r = start_task(start_ip="192.168.1.1", end_ip="192.168.1.254", port_scan=False,
                       resolve_hostname=False, concurrency=8, timeout_ms=500)
    tid4 = r["data"]["task_id"]
    await asyncio.sleep(1.5)
    st_s, r_s = http("POST", f"/api/scan/stop/{tid4}")
    check("stop 返回 200", st_s == 200 and r_s.get("success"), str(r_s))
    await asyncio.sleep(0.8)
    st, r = http("GET", f"/api/scan/result/{tid4}")
    d4 = r.get("data") or {}
    check("停止后状态=stopped", d4.get("status") == "stopped", f"status={d4.get('status')} scanned={d4.get('scanned')}")
    check("停止前已扫计数保留(>0)", (d4.get("scanned") or 0) > 0, f"scanned={d4.get('scanned')}")
    check("stop 不存在任务 -> 404", http("POST", "/api/scan/stop/nonexist")[0] == 404)

    print("\n== 8. 单任务约束：启动新任务应终止旧任务 ==")
    st, r = start_task(start_ip="10.99.1.1", end_ip="10.99.1.250", concurrency=8, timeout_ms=800,
                       resolve_hostname=False)
    tidA = r["data"]["task_id"]
    await asyncio.sleep(0.5)
    st, r = start_task(start_ip="127.0.0.1", end_ip="127.0.0.1", port_scan=True, ports=[lport],
                       concurrency=8, timeout_ms=300, resolve_hostname=False)
    tidB = r["data"]["task_id"]
    await asyncio.sleep(1.0)
    dA = http("GET", f"/api/scan/result/{tidA}")[1].get("data") or {}
    check("旧任务被终止(stopped/done)", dA.get("status") in ("stopped", "done"), f"A.status={dA.get('status')}")
    framesB, _ = await collect_scan(tidB, timeout=20)
    check("新任务正常运行并 done", any(f.get("type") == "done" for f in framesB),
          f"B frames={[f.get('type') for f in framesB][:6]}")

    print("\n== 9. 导出 CSV ==")
    st, r = http("POST", "/api/scan/export", {
        "items": [
            {"ip": "192.168.1.7", "mac": "3C:5A:B4:CC:DD:02", "vendor": "Google, Inc.",
             "hostname": "plc", "delay_ms": 3, "ports": [502], "online": True, "note": "3号泊位PLC"},
            {"ip": "192.168.1.9", "mac": "", "online": False, "note": ""},
        ],
        "directory": OUT, "filename": "qa_export.csv"})
    p = (r.get("data") or {}).get("path", "")
    check("export 200 且文件落地", st == 200 and os.path.exists(p), f"st={st} path={p}")
    if os.path.exists(p):
        with open(p, "rb") as f:
            check("导出 CSV 带 BOM", f.read(3) == b"\xef\xbb\xbf")
    check("export 无 items 无 task -> 400", http("POST", "/api/scan/export", {"items": []})[0] == 400)
    # task_id 兜底
    st, r = http("POST", "/api/scan/export", {"items": [], "task_id": tid3, "directory": OUT, "filename": "qa_export_taskid.csv"})
    check("export 用 task_id 兜底 200", st == 200 and os.path.exists((r.get("data") or {}).get("path", "")), str(r))

    print("\n== 10. 持久化 store（备份/还原用户数据）==")
    st, r = http("GET", "/api/store/app_data")
    original = ((r.get("data") or {}).get("value")) if st == 200 else None
    check("读取 app_data 成功", st == 200, f"st={st}")
    try:
        payload = {
            "quickCommands": [{"name": "KEEP", "data": "AA"}],
            "na_scan_notes": {"192.168.1.7": "3号泊位PLC"},
            "na_scan_favorites": {"192.168.1.7": True},
            "na_scan_history": [{"time": "10-14 15:00", "seg": "192.168.1.1-254", "total": 254, "online": 12, "devices": []}],
            "na_scan_config": {"concurrency": 64, "portScan": True, "ports": [502]},
        }
        st, _ = http("PUT", "/api/store/app_data", {"value": payload})
        check("写入 app_data 200", st == 200)
        st, r = http("GET", "/api/store/app_data")
        v = (r.get("data") or {}).get("value") or {}
        check("回读 na_scan_notes 一致", v.get("na_scan_notes") == {"192.168.1.7": "3号泊位PLC"}, str(v.get("na_scan_notes")))
        check("回读 na_scan_favorites 一致", v.get("na_scan_favorites") == {"192.168.1.7": True})
        check("回读 na_scan_history 一致", isinstance(v.get("na_scan_history"), list) and v["na_scan_history"][0]["online"] == 12)
        check("回读 na_scan_config 一致", v.get("na_scan_config", {}).get("ports") == [502])
        check("既有 key 未受污染", v.get("quickCommands") == [{"name": "KEEP", "data": "AA"}])
    finally:
        # 还原用户原始数据
        if original is None:
            http("PUT", "/api/store/app_data", {"value": {}})
        else:
            http("PUT", "/api/store/app_data", {"value": original})
        st, r = http("GET", "/api/store/app_data")
        v = (r.get("data") or {}).get("value") or {}
        check("已还原原始 store", v == (original if original is not None else {}) or (original is None and v == {}),
              "restored")

    print("\n== 11. 超级大范围（CIDR 上限保护 + 耗时）==")
    t0 = time.time()
    st, r = start_task(range="10.0.0.0/8")
    dt = time.time() - t0
    check("10.0.0.0/8 -> 400", st == 400, f"st={st} 耗时={dt:.2f}s detail={r.get('detail')}")
    print(f"       /8 拒绝耗时 {dt:.2f}s（观察事件循环阻塞）")

    print("\n===== 集成测试汇总 =====")
    print(f"  PASS {len(PASS)} / {len(PASS)+len(FAIL)}")
    for f in FAIL:
        print("   FAIL:", f)
    return 1 if FAIL else 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
