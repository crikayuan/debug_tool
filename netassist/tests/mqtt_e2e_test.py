# -*- coding: utf-8 -*-
"""
MQTT 端到端测试：连接公共 Broker → 订阅（含通配符）→ 对端收发 → 断言字节一致
→ 取消订阅 → 断开 → 重连恢复订阅 → 多实例 ClientID 唯一。

风格对齐 tests/e2e_test.py：
  python mqtt_e2e_test.py                 # 默认在 20031 端口自行拉起后端并测试
  python mqtt_e2e_test.py --base http://127.0.0.1:20031 --no-manage   # 复用已运行实例

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
import subprocess
import time
import uuid
import urllib.error
import urllib.request

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "backend"))
PEER = os.path.join(HERE, "mqtt_peer.py")

BROKER_HOST = "broker.emqx.io"
BROKER_PORT = 1883


def http(base, method, path, body=None, timeout=20):
    """简单 HTTP 封装：返回 (status, json)；HTTP 错误也返回其响应体。"""
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data else {}
    req = urllib.request.Request(base + path, data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode("utf-8"))
        except Exception:
            return e.code, {"detail": "no body"}


def start_backend(port):
    code = (
        "import sys;sys.path.insert(0,'.');"
        "import uvicorn;from main import app;"
        f"uvicorn.run(app,host='127.0.0.1',port={port},log_level='warning',access_log=False)"
    )
    return subprocess.Popen([sys.executable, "-c", code], cwd=BACKEND)


def wait_health(base, timeout=25):
    dl = time.time() + timeout
    while time.time() < dl:
        try:
            st, _ = http(base, "GET", "/health", timeout=3)
            if st == 200:
                return True
        except Exception:
            pass
        time.sleep(0.5)
    return False


async def ws_collector(ws_url, sink, stop_evt):
    """持续读取 WS，data 帧存入 sink。"""
    try:
        async with websockets.connect(ws_url, open_timeout=15) as ws:
            while not stop_evt.is_set():
                try:
                    raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
                except asyncio.TimeoutError:
                    continue
                d = json.loads(raw)
                if d.get("type") == "data":
                    sink.append(d)
    except Exception as e:
        print(f"    !! WS 异常: {e}")


async def wait_for_msg(sink, topic, timeout=10):
    dl = time.time() + timeout
    while time.time() < dl:
        for d in sink:
            if d.get("topic") == topic:
                return d
        await asyncio.sleep(0.1)
    return None


async def peer_pub(topic, payload, fmt="hex", qos=1, count=1, timeout=20):
    cmd = [sys.executable, PEER, "--host", BROKER_HOST, "--port", str(BROKER_PORT),
           "--topic", topic, "--mode", "pub", "--payload", payload, "--format", fmt,
           "--qos", str(qos), "--count", str(count)]
    return await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=timeout)


async def peer_sub(topic, qos=1, count=1, timeout=10):
    cmd = [sys.executable, PEER, "--host", BROKER_HOST, "--port", str(BROKER_PORT),
           "--topic", topic, "--mode", "sub", "--qos", str(qos),
           "--count", str(count), "--timeout", str(timeout)]
    return await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=timeout + 15)


async def main():
    global BROKER_HOST, BROKER_PORT

    ap = argparse.ArgumentParser(description="MQTT 端到端测试")
    ap.add_argument("--base", default="http://127.0.0.1:20031")
    ap.add_argument("--no-manage", action="store_true", help="不自动拉起后端，复用已运行实例")
    ap.add_argument("--broker-host", default=BROKER_HOST)
    ap.add_argument("--broker-port", type=int, default=BROKER_PORT)
    args = ap.parse_args()

    BROKER_HOST, BROKER_PORT = args.broker_host, args.broker_port

    base = args.base
    port = int(base.rsplit(":", 1)[1])
    proc = None
    if not args.no_manage:
        already = False
        try:
            st, _ = http(base, "GET", "/health", timeout=3)
            already = (st == 200)
        except Exception:
            already = False
        if not already:
            print(f"启动后端 :{port} ...")
            proc = start_backend(port)
    if not wait_health(base):
        print(f"!! 后端 {base} 未就绪，测试中止")
        if proc:
            proc.kill()
        sys.exit(1)
    print(f"后端就绪: {base}")

    suf = uuid.uuid4().hex[:6]
    root = f"test/e2e/{suf}"
    wildcard = f"{root}/+"
    topic_a = f"{root}/a"
    topic_b = f"{root}/b"
    topic_cmd = f"{root}/cmd"

    results = []

    def rec(desc, ok, extra=""):
        print(f"   [{'PASS' if ok else 'FAIL'}] {desc}{(' — ' + extra) if extra else ''}")
        results.append((desc, ok))

    cids = []

    # 1) 连接
    print("1) 连接 Broker")
    st, r = http(base, "POST", "/api/mqtt/connect",
                 {"host": BROKER_HOST, "port": BROKER_PORT, "client_id": "",
                  "username": "", "password": "", "keepalive": 60, "clean": True,
                  "reconnect": True, "reconnect_period": 4000, "client_id_with_time": False})
    ok = st == 200 and r.get("success") and r.get("data", {}).get("connection_id")
    cid = r.get("data", {}).get("connection_id") if r.get("data") else None
    client_id1 = r.get("data", {}).get("client_id") if r.get("data") else None
    cids.append(client_id1)
    rec("连接 Broker 成功", bool(ok), f"cid={cid} client_id={client_id1} ({st})")
    if not ok:
        _finish(results, proc)
        return

    # 2) 订阅通配符
    print("2) 订阅通配符主题")
    st, r = http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": wildcard, "qos": 1})
    await asyncio.sleep(1.2)
    st_s, status = http(base, "GET", f"/api/mqtt/status/{cid}")
    subs = status.get("subscriptions", [])
    rec("订阅通配符成功且 state=subscribed",
        st == 200 and any(s["topic"] == wildcard and s["state"] == "subscribed" for s in subs),
        f"subs={subs}")

    # 打开 WS 采集
    stop_evt = asyncio.Event()
    sink = []
    ws_url = base.replace("http", "ws") + f"/ws/mqtt/{cid}?encoding=utf-8"
    task = asyncio.create_task(ws_collector(ws_url, sink, stop_evt))
    await asyncio.sleep(1.5)

    # 3) 对端发 HEX（命中通配符 +）
    print("3) 对端发布 HEX → 前端 WS 接收（通配符 + 命中）")
    hex_bytes = bytes([0x01, 0x03, 0x04, 0x00, 0x1A, 0x00, 0x2B, 0x8C, 0x4E])
    expect_hex = hex_bytes.hex(" ").upper()
    pr = await peer_pub(topic_a, hex_bytes.hex(" "), fmt="hex", qos=1)
    got = await wait_for_msg(sink, topic_a, timeout=10)
    actual = got.get("hex_data") if got else None
    rec("WS 收到的 HEX 与发出字节一致", bool(got) and actual == expect_hex,
        f"期望 {expect_hex} / 实际 {actual}")

    # 4) 对端发文本（中文）
    print("4) 对端发布中文文本 → 字节一致")
    text = "泊位A03"
    expect_hex2 = text.encode("utf-8").hex(" ").upper()
    await peer_pub(topic_b, text, fmt="text", qos=0)
    got2 = await wait_for_msg(sink, topic_b, timeout=10)
    rec("WS 收到中文文本字节一致", bool(got2) and got2.get("hex_data") == expect_hex2,
        f"期望 {expect_hex2} / 实际 {got2.get('hex_data') if got2 else None}")

    # 5) 应用发布 → 对端收到（独立订阅者）
    print("5) 应用发布 → 对端收到字节一致")
    app_hex = "AA BB CC DD"
    peer_task = asyncio.create_task(peer_sub(topic_cmd, qos=1, count=1, timeout=10))
    await asyncio.sleep(1.8)  # 等对端订阅就绪
    st, r = http(base, "POST", f"/api/mqtt/publish/{cid}",
                 {"topic": topic_cmd, "payload": app_hex, "format": "hex", "qos": 1, "retain": False})
    peer_res = await peer_task
    ok5 = st == 200 and peer_res.returncode == 0 and "AA BB CC DD" in (peer_res.stdout or "")
    rec("应用发布被对端原样收到", ok5,
        f"publish={st} peer_rc={peer_res.returncode} out={ (peer_res.stdout or '').strip()[-80:] }")

    # 6) 取消订阅
    print("6) 取消订阅")
    st, r = http(base, "POST", f"/api/mqtt/unsubscribe/{cid}", {"topic": wildcard})
    await asyncio.sleep(0.8)
    st_s, status = http(base, "GET", f"/api/mqtt/status/{cid}")
    left = [s["topic"] for s in status.get("subscriptions", [])]
    rec("取消订阅后订阅表不再包含该主题", st == 200 and wildcard not in left, f"remaining={left}")

    # 7) 断开
    print("7) 断开连接")
    st, r = http(base, "POST", f"/api/mqtt/disconnect/{cid}")
    st_s, status = http(base, "GET", f"/api/mqtt/status/{cid}")
    rec("断开后 status.connected=False", st == 200 and status.get("connected") is False, f"{status}")

    # 8) 重连并恢复订阅
    print("8) 重连 + 恢复订阅（验证重连后可继续收报）")
    st, r = http(base, "POST", "/api/mqtt/connect", {"host": BROKER_HOST, "port": BROKER_PORT})
    cid2 = r.get("data", {}).get("connection_id") if r.get("data") else None
    client_id2 = r.get("data", {}).get("client_id") if r.get("data") else None
    cids.append(client_id2)
    http(base, "POST", f"/api/mqtt/subscribe/{cid2}", {"topic": topic_a, "qos": 1})
    await asyncio.sleep(1.2)
    sink2 = []
    stop2 = asyncio.Event()
    task2 = asyncio.create_task(ws_collector(
        base.replace("http", "ws") + f"/ws/mqtt/{cid2}?encoding=utf-8", sink2, stop2))
    await asyncio.sleep(1.5)
    await peer_pub(topic_a, "0A 0B", fmt="hex", qos=1)
    got8 = await wait_for_msg(sink2, topic_a, timeout=10)
    rec("重连并重新订阅后可继续收到消息",
        bool(got8) and got8.get("hex_data") == "0A 0B",
        f"实际 {got8.get('hex_data') if got8 else None}")

    # 9) 多实例 ClientID 唯一
    print("9) 多实例 ClientID 唯一")
    rec("两次连接自动生成的 ClientID 不同",
        cids[0] and cids[1] and cids[0] != cids[1], f"{cids}")

    # 收尾
    stop_evt.set()
    stop2.set()
    task.cancel()
    task2.cancel()
    http(base, "POST", f"/api/mqtt/disconnect/{cid2}")

    _finish(results, proc)


def _finish(results, proc):
    print("\n===== 结果汇总 =====")
    for d, ok in results:
        print(f"  [{'PASS' if ok else 'FAIL'}] {d}")
    passed = sum(1 for _, o in results if o)
    print(f"  {passed}/{len(results)} PASS")
    if proc:
        try:
            proc.kill()
        except Exception:
            pass
    sys.exit(0 if passed == len(results) and results else 1)


if __name__ == "__main__":
    asyncio.run(main())
