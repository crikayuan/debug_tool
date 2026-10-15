# -*- coding: utf-8 -*-
"""
MQTT 边缘与错误路径独立测试（QA 严过关 编写）。

在工程师 mqtt_e2e_test.py 之外，独立补齐：
  A. 连接错误路径（不可达 host / 错误端口 / 非法端口 / 空 host）—— 必须明确报错不挂死
  B. 未连接 / 不存在连接下的 REST 行为 —— 404 而非 500
  C. 重复订阅同一主题不产生重复项且不重置计数
  D. 取消一个不存在的订阅 —— 优雅失败
  E. 空 payload / 超长 payload（100KB 十六进制串）字节一致
  F. 中文与特殊字符 payload 字节一致
  G. 通配符边界：+ 单层（不多匹配）、# 多层（含父层）
  H. 连续快速发布 50 条 —— 不丢包、统计准确
  J. 两实例连同一 Broker —— ClientID 唯一、互不踢线

用法：
  python mqtt_edge_test.py                 # 在 20031/20032 自行拉起后端并测试
  python mqtt_edge_test.py --no-manage     # 复用已运行实例

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
import urllib.error
import urllib.request
import uuid

import websockets

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "backend"))
PEER = os.path.join(HERE, "mqtt_peer.py")

BROKER_HOST = "broker.emqx.io"
BROKER_PORT = 1883

# 禁用环境代理，避免本机 502（项目已知坑）
_NOPROXY = urllib.request.build_opener(urllib.request.ProxyHandler({}))


def http(base, method, path, body=None, timeout=25):
    """返回 (status, json)；HTTP 错误也返回其响应体。"""
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
    code = (
        "import sys;sys.path.insert(0,'.');"
        "import uvicorn;from main import app;"
        f"uvicorn.run(app,host='127.0.0.1',port={port},log_level='error',access_log=False)"
    )
    return subprocess.Popen([sys.executable, "-c", code], cwd=BACKEND)


def wait_health(base, timeout=25):
    dl = time.time() + timeout
    while time.time() < dl:
        st, _ = http(base, "GET", "/health", timeout=3)
        if st == 200:
            return True
        time.sleep(0.5)
    return False


async def ws_collector(ws_url, sink, stop_evt):
    """持续读取 WS，data 帧存入 sink；error 帧记录到 sink['errors']。"""
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
                elif d.get("type") == "error":
                    sink.setdefault("errors", []).append(d)
    except Exception as e:
        sink.setdefault("ws_exc", []).append(str(e))


async def wait_count(sink, topic, n, timeout=20):
    """等待 sink 中某个 topic 的 data 帧达到 n 条，返回实际条数。"""
    dl = time.time() + timeout
    while time.time() < dl:
        c = sum(1 for d in sink if d.get("topic") == topic)
        if c >= n:
            return c
        await asyncio.sleep(0.1)
    return sum(1 for d in sink if d.get("topic") == topic)


async def wait_for_msg(sink, topic, timeout=12):
    dl = time.time() + timeout
    while time.time() < dl:
        for d in sink:
            if d.get("topic") == topic:
                return d
        await asyncio.sleep(0.1)
    return None


async def peer_pub(topic, payload, fmt="hex", qos=0, count=1, interval=0.2, timeout=40):
    cmd = [sys.executable, PEER, "--host", BROKER_HOST, "--port", str(BROKER_PORT),
           "--topic", topic, "--mode", "pub", "--payload", payload, "--format", fmt,
           "--qos", str(qos), "--count", str(count), "--interval", str(interval)]
    return await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=timeout)


def rec(results, name, ok, extra=""):
    print(f"   [{'PASS' if ok else 'FAIL'}] {name}" + (f" — {extra}" if extra else ""))
    results.append((name, ok, extra))


def connect_broker(base, **kw):
    body = {"host": BROKER_HOST, "port": BROKER_PORT, "client_id": "", "username": "",
            "password": "", "keepalive": 60, "clean": True, "reconnect": True,
            "reconnect_period": 4000, "client_id_with_time": False}
    body.update(kw)
    return http(base, "POST", "/api/mqtt/connect", body)


async def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:20031")
    ap.add_argument("--base2", default="http://127.0.0.1:20032")
    ap.add_argument("--no-manage", action="store_true")
    args = ap.parse_args()

    base = args.base
    base2 = args.base2
    port = int(base.rsplit(":", 1)[1])
    port2 = int(base2.rsplit(":", 1)[1])

    procs = []
    if not args.no_manage:
        st, _ = http(base, "GET", "/health", timeout=3)
        if st != 200:
            print(f"启动后端 :{port} ...")
            procs.append(start_backend(port))
    if not wait_health(base):
        print(f"!! 后端 {base} 未就绪")
        for p in procs:
            p.kill()
        sys.exit(1)
    print(f"后端就绪: {base}")

    suf = uuid.uuid4().hex[:6]
    results = []
    cids = []

    # ============ A. 连接错误路径 ============
    print("A) 连接错误路径（必须明确报错、不挂死）")
    t0 = time.time()
    st, r = http(base, "POST", "/api/mqtt/connect", {"host": "127.0.0.1", "port": 1, "keepalive": 60})
    dt = time.time() - t0
    rec(results, "端口拒绝(127.0.0.1:1) 返回 4xx 且有明确错误",
        st == 400 and ("连接失败" in (r.get("detail", "") or r.get("message", ""))), f"st={st} dt={dt:.1f}s detail={r.get('detail')!r}")
    rec(results, "端口拒绝场景不挂死(<12s)", dt < 12, f"耗时 {dt:.1f}s")

    t0 = time.time()
    st, r = http(base, "POST", "/api/mqtt/connect", {"host": "no-such-host-qa.invalid", "port": 1883})
    dt = time.time() - t0
    rec(results, "域名不可解析返回 4xx 且有明确错误",
        st == 400, f"st={st} dt={dt:.1f}s detail={r.get('detail')!r}")
    rec(results, "域名不可解析场景不挂死(<12s)", dt < 12, f"耗时 {dt:.1f}s")

    st, r = http(base, "POST", "/api/mqtt/connect", {"host": "", "port": 1883})
    rec(results, "空 host 返回 400", st == 400, f"st={st} detail={r.get('detail')!r}")

    st, r = http(base, "POST", "/api/mqtt/connect", {"host": "broker.emqx.io", "port": 0})
    rec(results, "端口 0 返回 400", st == 400, f"st={st} detail={r.get('detail')!r}")

    st, r = http(base, "POST", "/api/mqtt/connect", {"host": "broker.emqx.io", "port": 70000})
    rec(results, "端口 70000 返回 400", st == 400, f"st={st} detail={r.get('detail')!r}")

    # ============ B. 不存在连接 / 未连接的 REST 行为 ============
    print("B) 不存在连接 / 未连接下的 REST 行为（404 而非 500）")
    ghost = "mqtt:ghost-host:1883"
    st, r = http(base, "POST", f"/api/mqtt/publish/{ghost}", {"topic": "x", "payload": "01", "format": "hex"})
    rec(results, "publish 到不存在连接 → 404", st == 404, f"st={st} detail={r.get('detail')!r}")
    st, r = http(base, "POST", f"/api/mqtt/subscribe/{ghost}", {"topic": "x", "qos": 0})
    rec(results, "subscribe 到不存在连接 → 404", st == 404, f"st={st} detail={r.get('detail')!r}")
    st, r = http(base, "POST", f"/api/mqtt/unsubscribe/{ghost}", {"topic": "x"})
    rec(results, "unsubscribe 到不存在连接 → 404", st == 404, f"st={st} detail={r.get('detail')!r}")
    st, r = http(base, "POST", f"/api/mqtt/disconnect/{ghost}")
    rec(results, "disconnect 不存在连接 → 404", st == 404, f"st={st} detail={r.get('detail')!r}")
    st, r = http(base, "GET", f"/api/mqtt/status/{ghost}")
    rec(results, "status 不存在连接 → 200 {connected:false}",
        st == 200 and r.get("connected") is False, f"st={st} body={r}")
    st, r = http(base, "GET", f"/api/mqtt/subscriptions/{ghost}")
    rec(results, "subscriptions 不存在连接 → 200 空表",
        st == 200 and r.get("data", {}).get("subscriptions") == [], f"st={st} body={r}")

    # WS 连到不存在连接 → error 帧
    err_sink = {}
    stop_evt0 = asyncio.Event()
    t0task = asyncio.create_task(ws_collector(base.replace("http", "ws") + f"/ws/mqtt/{ghost}", err_sink, stop_evt0))
    await asyncio.sleep(1.5)
    stop_evt0.set()
    t0task.cancel()
    rec(results, "WS 连不存在连接 → 收到 error 帧(连接不存在)",
        bool(err_sink.get("errors")), f"errors={err_sink.get('errors')}")

    # ============ 建立主连接 ============
    print("C) 建立主连接并做订阅相关边缘校验")
    st, r = connect_broker(base)
    ok = st == 200 and r.get("success")
    cid = (r.get("data") or {}).get("connection_id")
    cids.append((r.get("data") or {}).get("client_id"))
    rec(results, "连接 Broker 成功", bool(ok), f"cid={cid} st={st}")
    if not ok:
        _finish(results, procs, [])

    root = f"qa/edge/{suf}"
    # 空 topic 校验
    st, r = http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": "   ", "qos": 0})
    rec(results, "空订阅主题 → 400", st == 400, f"st={st} detail={r.get('detail')!r}")
    st, r = http(base, "POST", f"/api/mqtt/publish/{cid}", {"topic": "  ", "payload": "01", "format": "hex"})
    rec(results, "空发布主题 → 400", st == 400, f"st={st} detail={r.get('detail')!r}")

    # 打开 WS 采集（用于后续接收类用例）
    sink = []
    stop_evt = asyncio.Event()
    ws_task = asyncio.create_task(
        ws_collector(base.replace("http", "ws") + f"/ws/mqtt/{cid}?encoding=utf-8", sink, stop_evt))
    await asyncio.sleep(1.2)

    # ============ C2. 重复订阅 ============
    print("C2) 重复订阅同一主题")
    dup_topic = f"{root}/dup"
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": dup_topic, "qos": 0})
    await asyncio.sleep(0.8)
    # 先收一条，验证计数=1
    await peer_pub(dup_topic, "11", fmt="hex", qos=0)
    await wait_count(sink, dup_topic, 1, timeout=12)
    await asyncio.sleep(0.5)
    # 再次订阅同一主题
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": dup_topic, "qos": 0})
    await asyncio.sleep(0.8)
    st, r = http(base, "GET", f"/api/mqtt/subscriptions/{cid}")
    subs = r.get("data", {}).get("subscriptions", [])
    dup_entries = [s for s in subs if s["topic"] == dup_topic]
    rec(results, "重复订阅不产生重复项（唯一）", len(dup_entries) == 1, f"entries={dup_entries}")
    rec(results, "重复订阅不重置该主题消息计数", bool(dup_entries) and dup_entries[0]["count"] >= 1,
        f"count={dup_entries[0]['count'] if dup_entries else None}")

    # ============ D. 取消不存在的订阅 ============
    print("D) 取消一个不存在的订阅")
    st, r = http(base, "POST", f"/api/mqtt/unsubscribe/{cid}", {"topic": f"{root}/never-subscribed"})
    rec(results, "取消不存在订阅 → 非 500（优雅失败）", st in (200, 400, 404), f"st={st} detail={r.get('detail')!r}")

    # ============ E. 空 payload / 超长 payload ============
    print("E) 空 payload 与超长 payload")
    empty_topic = f"{root}/empty"
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": empty_topic, "qos": 0})
    await asyncio.sleep(0.9)
    before_stats = http(base, "GET", f"/api/mqtt/status/{cid}")[1].get("stats", {})
    st, r = http(base, "POST", f"/api/mqtt/publish/{cid}",
                 {"topic": empty_topic, "payload": "", "format": "text", "qos": 0})
    got_empty = await wait_for_msg(sink, empty_topic, timeout=10)
    rec(results, "空 payload 发布 → 200 且对端(本端订阅)收到 length=0",
        st == 200 and got_empty is not None and got_empty.get("length") == 0,
        f"st={st} got={got_empty}")

    # 超长 payload：100KB 十六进制串（51200 字节）—— 由本端发布，独立对端订阅校验字节一致
    big_bytes = bytes((i * 7 + 13) % 256 for i in range(51200))
    big_hex = big_bytes.hex(" ")  # hex 字符串约 153KB 字符
    big_topic = f"{root}/big"
    peer_task = asyncio.create_task(peer_sub(big_topic, qos=0, count=1, timeout=25))
    await asyncio.sleep(2.0)
    st, r = http(base, "POST", f"/api/mqtt/publish/{cid}",
                 {"topic": big_topic, "payload": big_hex.replace(" ", ""), "format": "hex", "qos": 0})
    peer_res = await peer_task
    expect = big_bytes.hex(" ").upper()
    got_hex = ""
    for line in (peer_res.stdout or "").splitlines():
        if "hex=" in line:
            got_hex = line.split("hex=", 1)[1].strip()
    rec(results, "超长 payload(51200B/100KB hex) 发布被对端字节一致收到",
        st == 200 and peer_res.returncode == 0 and got_hex.replace(" ", "") == expect.replace(" ", ""),
        f"publish_st={st} peer_rc={peer_res.returncode} got_len={len(got_hex)}")

    # ============ F. 中文与特殊字符 ============
    print("F) 中文与特殊字符 payload 字节一致")
    special = "泊位A03·中文&特殊<>\r\n\t=?%$#"
    sp_topic = f"{root}/special"
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": sp_topic, "qos": 1})
    await asyncio.sleep(0.9)
    await peer_pub(sp_topic, special, fmt="text", qos=1)
    got_sp = await wait_for_msg(sink, sp_topic, timeout=12)
    rec(results, "中文+特殊字符 payload 字节一致(UTF-8)",
        got_sp is not None and got_sp.get("hex_data") == special.encode("utf-8").hex(" ").upper(),
        f"期望 {special.encode('utf-8').hex(' ').upper()} / 实际 {got_sp.get('hex_data') if got_sp else None}")

    # ============ G. 通配符边界 ============
    print("G) 通配符边界")
    wc_root = f"{root}/wc"
    single = f"{wc_root}/+/c"
    multi = f"{wc_root}/#"
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": single, "qos": 0})
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": multi, "qos": 0})
    await asyncio.sleep(1.2)

    # + 命中单层
    await peer_pub(f"{wc_root}/b/c", "A1", fmt="hex", qos=0)
    hit_plus = await wait_for_msg(sink, f"{wc_root}/b/c", timeout=12)
    rec(results, "+ 命中单层 a/b/c", hit_plus is not None, f"got={hit_plus}")
    # + 不多匹配多一层
    await peer_pub(f"{wc_root}/b/c/d", "A2", fmt="hex", qos=0)
    await asyncio.sleep(2.5)
    over = [d for d in sink if d.get("topic") == f"{wc_root}/b/c/d"]
    # 该层被 multi(#) 命中属正常；关键看 single(+) 是否越界命中无法直接从 WS 区分，
    # 但 # 命中是预期，故此处仅校验 # 命中了它、且 + 主题未受污染（用 is_plus 单独验证见下）
    rec(results, "# 命中多层 a/b/c/d", len(over) >= 1, f"got {len(over)} 条")
    # # 命中父层（wc_root 本身）
    await peer_pub(wc_root, "A3", fmt="hex", qos=0)
    hit_parent = await wait_for_msg(sink, wc_root, timeout=12)
    rec(results, "# 命中父层 wc_root", hit_parent is not None, f"got={hit_parent}")

    # 单独验证 + 越界：新开一条只订阅 + 的独立主题前缀，避免 # 干扰
    plus_only_root = f"{root}/plusonly"
    plus_pat = f"{plus_only_root}/+/c"
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": plus_pat, "qos": 0})
    http(base, "POST", f"/api/mqtt/unsubscribe/{cid}", {"topic": f"{plus_only_root}/#"})  # 确认无 #
    await asyncio.sleep(1.0)
    await peer_pub(f"{plus_only_root}/b/c/d", "B1", fmt="hex", qos=0)
    await asyncio.sleep(2.5)
    leaked = [d for d in sink if d.get("topic") == f"{plus_only_root}/b/c/d"]
    rec(results, "+ 不多匹配多一层（a/+/c 不匹配 a/b/c/d）", len(leaked) == 0, f"误收 {len(leaked)} 条")
    await peer_pub(f"{plus_only_root}/b/c", "B2", fmt="hex", qos=0)
    plus_hit = await wait_for_msg(sink, f"{plus_only_root}/b/c", timeout=12)
    rec(results, "+ 仍正常匹配单层 a/b/c", plus_hit is not None, f"got={plus_hit}")

    # ============ H. 连续快速发布 50 条 ============
    # 说明：QoS0 为「至多一次」best-effort，公共 Broker 在突发下会丢弃（实测 20@0.02s 仅到 10），
    #       故「无丢包」断言必须用 QoS1（有 PUBACK，实测同速率 20/20）。QoS0 仅作观测记录。
    print("H) 连续快速发布 50 条（QoS1 不丢包 + 统计准确；QoS0 观测）")
    rapid_topic = f"{root}/rapid"
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": rapid_topic, "qos": 1})
    await asyncio.sleep(1.2)
    before = sum(1 for d in sink if d.get("topic") == rapid_topic)
    await peer_pub(rapid_topic, "5A", fmt="hex", qos=1, count=50, interval=0.02, timeout=90)
    got_n = await wait_count(sink, rapid_topic, 50, timeout=40)
    rec(results, "QoS1 快速发布 50 条全部收到（无丢包）", got_n - before >= 50, f"收到 {got_n - before}/50")
    st_s, status = http(base, "GET", f"/api/mqtt/status/{cid}")
    rec(results, "订阅表 count 统计准确(>=50)", any(
        s["topic"] == rapid_topic and s["count"] >= 50 for s in status.get("subscriptions", [])),
        f"subs={[(s['topic'], s['count']) for s in status.get('subscriptions', []) if s['topic'] == rapid_topic]}")

    # QoS0 突发观测（不计入通过判据，仅记录 best-effort 丢失特征）
    q0_topic = f"{root}/rapid0"
    http(base, "POST", f"/api/mqtt/subscribe/{cid}", {"topic": q0_topic, "qos": 0})
    await asyncio.sleep(1.0)
    b0 = sum(1 for d in sink if d.get("topic") == q0_topic)
    await peer_pub(q0_topic, "6B", fmt="hex", qos=0, count=50, interval=0.02, timeout=60)
    await asyncio.sleep(6)
    got0 = sum(1 for d in sink if d.get("topic") == q0_topic) - b0
    print(f"   [INFO] QoS0 突发 50 条实际到达 {got0}/50（best-effort，允许丢失）")
    st0, stt0 = http(base, "GET", f"/api/mqtt/status/{cid}")
    c0 = next((s["count"] for s in stt0.get("subscriptions", []) if s["topic"] == q0_topic), None)
    rec(results, "QoS0 场景：订阅 count 与实际到达一致（无虚计/漏计）", c0 == got0, f"count={c0} ws={got0}")

    # ============ J. 两实例多开 ============
    # 先停掉前面测试遗留的 WS 消费协程，避免与同一 connection_id 的新消费端争抢队列
    stop_evt.set()
    ws_task.cancel()
    await asyncio.sleep(0.5)
    print("J) 两实例连同一 Broker")
    proc2 = None
    if not args.no_manage:
        st2, _ = http(base2, "GET", "/health", timeout=3)
        if st2 != 200:
            proc2 = start_backend(port2)
            procs.append(proc2)
    if wait_health(base2):
        st, r1 = connect_broker(base)
        cidA = (r1.get("data") or {}).get("connection_id")
        cidA_id = (r1.get("data") or {}).get("client_id")
        st, r2 = connect_broker(base2)
        cidB = (r2.get("data") or {}).get("connection_id")
        cidB_id = (r2.get("data") or {}).get("client_id")
        rec(results, "两实例自动 ClientID 不同", bool(cidA_id and cidB_id and cidA_id != cidB_id),
            f"{cidA_id} vs {cidB_id}")
        multi_topic = f"{root}/multi"
        http(base, "POST", f"/api/mqtt/subscribe/{cidA}", {"topic": multi_topic, "qos": 1})
        http(base, "POST", f"/api/mqtt/subscribe/{cidB}", {"topic": multi_topic, "qos": 1})
        await asyncio.sleep(2.0)
        sinkA2, sinkB2 = [], []
        stopA, stopB = asyncio.Event(), asyncio.Event()
        tA = asyncio.create_task(ws_collector(base.replace("http", "ws") + f"/ws/mqtt/{cidA}?encoding=utf-8", sinkA2, stopA))
        tB = asyncio.create_task(ws_collector(base2.replace("http", "ws") + f"/ws/mqtt/{cidB}?encoding=utf-8", sinkB2, stopB))
        await asyncio.sleep(2.5)
        peer_rcs = []
        for i in range(3):
            pr = await peer_pub(multi_topic, f"0{i+1}", fmt="hex", qos=1)
            peer_rcs.append(pr.returncode)
            await asyncio.sleep(1.2)
        await asyncio.sleep(1.5)
        gotA = sum(1 for d in sinkA2 if d.get("topic") == multi_topic)
        gotB = sum(1 for d in sinkB2 if d.get("topic") == multi_topic)
        _, sA = http(base, "GET", f"/api/mqtt/status/{cidA}")
        _, sB = http(base2, "GET", f"/api/mqtt/status/{cidB}")
        cntA = next((s["count"] for s in sA.get("subscriptions", []) if s["topic"] == multi_topic), 0)
        cntB = next((s["count"] for s in sB.get("subscriptions", []) if s["topic"] == multi_topic), 0)
        rec(results, "同一消息被两实例后端同时收到（互不踢线）",
            cntA >= 3 and cntB >= 3, f"A={cntA}/3 B={cntB}/3 (ws A={gotA} B={gotB}) peer_rc={peer_rcs}")
        stA, statusA = http(base, "GET", f"/api/mqtt/status/{cidA}")
        stB, statusB = http(base2, "GET", f"/api/mqtt/status/{cidB}")
        rec(results, "两实例均保持 connected=True",
            statusA.get("connected") is True and statusB.get("connected") is True,
            f"A={statusA.get('connected')} B={statusB.get('connected')}")
        stopA.set(); stopB.set(); tA.cancel(); tB.cancel()
        http(base, "POST", f"/api/mqtt/disconnect/{cidA}")
        http(base2, "POST", f"/api/mqtt/disconnect/{cidB}")
    else:
        rec(results, "两实例多开（第二实例未就绪，跳过）", False, "base2 未就绪")

    # 收尾
    stop_evt.set()
    ws_task.cancel()
    http(base, "POST", f"/api/mqtt/disconnect/{cid}")

    _finish(results, procs)


async def peer_sub(topic, qos=0, count=1, timeout=25):
    cmd = [sys.executable, PEER, "--host", BROKER_HOST, "--port", str(BROKER_PORT),
           "--topic", topic, "--mode", "sub", "--qos", str(qos),
           "--count", str(count), "--timeout", str(timeout)]
    return await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True, timeout=timeout + 20)


def _finish(results, procs):
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
