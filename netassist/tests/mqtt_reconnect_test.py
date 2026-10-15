# -*- coding: utf-8 -*-
"""
MQTT 断线自动重连 + 订阅恢复 独立测试（QA 严过关 编写）—— 验证核心需求 R-10 / AC-12。

方案：在后端与真实 Broker 之间插入一个**本地 TCP 转发代理**，
     后端连到代理（而不是直连 Broker）。
     - 关闭代理 → 后端与 Broker 之间 TCP 断开（非人工 disconnect）→ paho 触发自动重连
     - 重启代理 → paho 重连成功 → on_connect 无条件重放订阅表
     - 由独立对端经真实 Broker 发布消息 → 若后端仍能收到，即证明订阅已自动恢复

这样可真实复现「网络抖动断开后自动重连并恢复订阅」，而不是重新调一次 connect API。

用法：
  python mqtt_reconnect_test.py            # 自行在 20031 拉起后端
  python mqtt_reconnect_test.py --no-manage
退出码：全部通过为 0，否则为 1。
"""
import sys

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import argparse
import asyncio
import json
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "backend"))
PEER = os.path.join(HERE, "mqtt_peer.py")

BROKER_HOST = "broker.emqx.io"
BROKER_PORT = 1883
PROXY_HOST = "127.0.0.1"
PROXY_PORT = 18830

_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


class TcpProxy:
    """把 127.0.0.1:listen_port 的流量转发到 target；可反复 start/stop。"""

    def __init__(self, listen_port, target_host, target_port):
        self.listen_port = listen_port
        self.target = (target_host, target_port)
        self._srv = None
        self._conns = []
        self._lock = threading.Lock()
        self._running = False

    def start(self):
        self._srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._srv.bind((PROXY_HOST, self.listen_port))
        self._srv.listen(16)
        self._srv.settimeout(0.3)
        self._running = True
        threading.Thread(target=self._accept_loop, daemon=True).start()
        time.sleep(0.2)
        return self

    def _accept_loop(self):
        while self._running:
            try:
                c, _ = self._srv.accept()
            except socket.timeout:
                continue
            except OSError:
                break
            with self._lock:
                self._conns.append(c)
            threading.Thread(target=self._pipe, args=(c,), daemon=True).start()

    def _pipe(self, client):
        try:
            up = socket.create_connection(self.target, timeout=8)
        except Exception:
            try:
                client.close()
            except Exception:
                pass
            return
        with self._lock:
            self._conns.append(up)

        def fwd(a, b):
            try:
                while True:
                    data = a.recv(65536)
                    if not data:
                        break
                    b.sendall(data)
            except Exception:
                pass
            finally:
                for s in (a, b):
                    try:
                        s.shutdown(socket.SHUT_RDWR)
                    except Exception:
                        pass

        threading.Thread(target=fwd, args=(client, up), daemon=True).start()
        fwd(up, client)

    def stop(self):
        self._running = False
        try:
            self._srv.close()
        except Exception:
            pass
        with self._lock:
            for s in self._conns:
                try:
                    s.close()
                except Exception:
                    pass
            self._conns.clear()
        time.sleep(0.2)


def http(base, method, path, body=None, timeout=25):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with _NOPROXY.open(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"detail": "no body"}
    except Exception as e:
        return -1, {"detail": f"request error: {e}"}


def start_backend(port):
    code = ("import sys;sys.path.insert(0,'.');import uvicorn;from main import app;"
            f"uvicorn.run(app,host='127.0.0.1',port={port},log_level='error',access_log=False)")
    return subprocess.Popen([sys.executable, "-c", code], cwd=BACKEND)


def wait_health(base, timeout=25):
    dl = time.time() + timeout
    while time.time() < dl:
        if http(base, "GET", "/health", timeout=3)[0] == 200:
            return True
        time.sleep(0.5)
    return False


async def ws_collector(ws_url, sink, stop_evt):
    try:
        async with websockets.connect(ws_url, open_timeout=15, max_size=None) as ws:
            while not stop_evt.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                if d.get("type") == "data":
                    sink.append(d)
    except Exception as e:
        sink.setdefault("ws_exc", []).append(str(e))


async def wait_for_msg(sink, topic, timeout=15):
    dl = time.time() + timeout
    while time.time() < dl:
        for d in sink:
            if d.get("topic") == topic:
                return d
        await asyncio.sleep(0.1)
    return None


async def peer_pub(topic, payload, fmt="hex", qos=1, timeout=40):
    cmd = [sys.executable, PEER, "--host", BROKER_HOST, "--port", str(BROKER_PORT),
           "--topic", topic, "--mode", "pub", "--payload", payload, "--format", fmt,
           "--qos", str(qos), "--count", "1"]
    return await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=timeout)


def rec(results, name, ok, extra=""):
    print(f"   [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))
    results.append((name, ok, extra))


def poll_connected(base, cid, want, deadline_s):
    """轮询连接状态，返回 (达成?, 耗时s, 最后状态)。"""
    t0 = time.time()
    last = None
    while time.time() - t0 < deadline_s:
        st, s = http(base, "GET", f"/api/mqtt/status/{cid}")
        last = s
        if s.get("connected") is want:
            return True, time.time() - t0, s
        time.sleep(0.5)
    return False, time.time() - t0, last


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:20031")
    ap.add_argument("--no-manage", action="store_true")
    args = ap.parse_args()
    base = args.base
    port = int(base.rsplit(":", 1)[1])

    procs = []
    if not args.no_manage:
        if http(base, "GET", "/health", timeout=3)[0] != 200:
            print(f"启动后端 :{port} ...")
            procs.append(start_backend(port))
    if not wait_health(base):
        print("!! 后端未就绪")
        for p in procs:
            p.kill()
        sys.exit(1)
    print(f"后端就绪: {base}")

    results = []
    suf = uuid.uuid4().hex[:6]
    topic = f"qa/reconn/{suf}/data"

    proxy = TcpProxy(PROXY_PORT, BROKER_HOST, BROKER_PORT).start()
    print(f"本地代理已启动 {PROXY_HOST}:{PROXY_PORT} -> {BROKER_HOST}:{BROKER_PORT}")

    try:
        # 1) 通过代理连接（开启自动重连，缩短重连周期加速验证）
        st, r = http(base, "POST", "/api/mqtt/connect", {
            "host": PROXY_HOST, "port": PROXY_PORT, "client_id": "",
            "username": "", "password": "", "keepalive": 15, "clean": True,
            "reconnect": True, "reconnect_period": 1000, "client_id_with_time": False})
        ok = st == 200 and r.get("success")
        cid = (r.get("data") or {}).get("connection_id")
        rec(results, "经本地代理连接 Broker 成功", bool(ok), f"cid={cid} st={st} detail={r.get('detail')}")
        if not ok:
            _finish(results, procs, proxy)

        # 2) 订阅
        st, r = http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": topic, "qos": 1})
        await asyncio.sleep(1.2)
        st_s, status = http(base, "GET", f"/api/mqtt/status/{cid}")
        rec(results, "订阅成功且 state=subscribed",
            any(s["topic"] == topic and s["state"] == "subscribed" for s in status.get("subscriptions", [])),
            f"subs={status.get('subscriptions')}")

        # 3) WS 采集 + 基线收发
        sink = []
        stop_evt = asyncio.Event()
        ws_task = asyncio.create_task(
            ws_collector(base.replace("http", "ws") + f"/ws/mqtt/{cid}?encoding=utf-8", sink, stop_evt))
        await asyncio.sleep(1.2)
        await peer_pub(topic, "01", fmt="hex", qos=1)
        base_msg = await wait_for_msg(sink, topic, timeout=15)
        rec(results, "断线前可正常收报（基线）", base_msg is not None and base_msg.get("hex_data") == "01",
            f"got={base_msg.get('hex_data') if base_msg else None}")

        # 4) 断开代理（模拟网络抖动）
        print("模拟网络抖动：关闭本地代理 ...")
        proxy.stop()
        recovered_dis, dt_dis, last_dis = await asyncio.to_thread(poll_connected, base, cid, False, 12)
        rec(results, "断开后状态置为未连接（检测到掉线）", recovered_dis, f"耗时 {dt_dis:.1f}s status={last_dis.get('connected') if isinstance(last_dis, dict) else last_dis}")

        # 5) 恢复代理 → 期待 paho 自动重连
        print("恢复本地代理，等待 paho 自动重连 ...")
        proxy.start()
        reconnected, dt_rc, last_rc = await asyncio.to_thread(poll_connected, base, cid, True, 30)
        rec(results, "代理恢复后自动重连成功（无需人工 connect）", reconnected, f"耗时 {dt_rc:.1f}s")

        # 6) 重连后订阅表仍在且 state=subscribed（on_connect 重放后应回到 subscribed）
        await asyncio.sleep(1.5)
        st_s, status = http(base, "GET", f"/api/mqtt/status/{cid}")
        subs = status.get("subscriptions", [])
        rec(results, "重连后订阅表仍在",
            any(s["topic"] == topic for s in subs), f"subs={subs}")

        # 7) 重连后仍能收到订阅主题的消息 → 证明订阅已自动恢复
        await peer_pub(topic, "0B", fmt="hex", qos=1)
        after = await wait_for_msg(sink, topic, timeout=15)
        got_after = any(d.get("topic") == topic and d.get("hex_data") == "0B" for d in sink)
        rec(results, "重连后可继续收到订阅主题消息（订阅自动恢复）", got_after,
            f"最近帧={after.get('hex_data') if after else None}")

        stop_evt.set()
        ws_task.cancel()
        http(base, "POST", f"/api/mqtt/disconnect/{cid}")

    finally:
        proxy.stop()

    _finish(results, procs, proxy)


def _finish(results, procs, proxy=None):
    print("\n===== 结果汇总 =====")
    for name, ok, extra in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))
    passed = sum(1 for _, o, _ in results if o)
    print(f"  {passed}/{len(results)} PASS")
    for p in procs:
        try:
            p.kill()
        except Exception:
            pass
    sys.exit(0 if results and passed == len(results) else 1)


if __name__ == "__main__":
    asyncio.run(main())
