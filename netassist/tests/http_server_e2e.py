# -*- coding: utf-8 -*-
"""HTTP Server 模块集成测试：真实 uvicorn 后端 + REST + WebSocket 实时推送。"""
import asyncio
import json
import subprocess
import sys
import time
import http.client

import websockets

PY = r"C:\Users\yuanj\.workbuddy\binaries\python\envs\netassist\Scripts\python.exe"
BE = r"D:\workbuddy\2026-10-10-14-59-54\netassist\backend"
API_PORT = 20035
HTTP_PORT = 18082
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (("  -> " + str(detail)) if detail else ""))


def api(method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", API_PORT, timeout=10)
    conn.request(method, path,
                 body=json.dumps(body).encode() if body is not None else None,
                 headers={"Content-Type": "application/json"})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    try:
        return resp.status, json.loads(data.decode("utf-8"))
    except Exception:
        return resp.status, data


def hit(method, path, body=b"", headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", HTTP_PORT, timeout=10)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    st = resp.status
    conn.close()
    return st, data


async def ws_flow(session_id):
    """连上 WS，然后在另一侧发真实 HTTP 请求，验证实时推送。"""
    url = "ws://127.0.0.1:%d/ws/http/%s" % (API_PORT, session_id)
    got = {}
    async with websockets.connect(url) as ws:
        # 建立连接后小睡，确保服务端已进入轮询
        await asyncio.sleep(0.3)
        # 后台发请求（同步调用放线程）
        await asyncio.to_thread(
            hit, "POST", "/ws-live?from=ws", b'{"k":"v"}', {"Content-Type": "application/json"}
        )
        await asyncio.to_thread(hit, "GET", "/ws-second")
        deadline = time.time() + 6
        while time.time() < deadline and len(got) < 2:
            try:
                raw = await asyncio.wait_for(ws.recv(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            msg = json.loads(raw)
            if msg.get("type") == "request":
                got[msg["data"]["path"]] = msg["data"]
    return got


proc = subprocess.Popen(
    [PY, "-m", "uvicorn", "main:app", "--host", "127.0.0.1", "--port", str(API_PORT), "--log-level", "warning"],
    cwd=BE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
)
try:
    ready = False
    for _ in range(40):
        time.sleep(0.5)
        try:
            st, _d = api("GET", "/health")
            if st == 200:
                ready = True
                break
        except Exception:
            pass
    check("后端就绪", ready)
    if not ready:
        raise SystemExit(1)

    st, d = api("GET", "/api/http-server/status")
    check("status 未运行", st == 200 and d["data"]["running"] is False, d)

    st, d = api("POST", "/api/http-server/start", {
        "port": HTTP_PORT, "bind": "127.0.0.1",
        "response": {"code": 200, "content_type": "application/json", "body": "", "delay_ms": 0, "echo": True},
    })
    check("REST 启动服务", st == 200 and d["success"], d)
    sid = d["data"]["session_id"]
    check("返回 addresses", len(d["data"]["addresses"]) > 0)

    st, d = api("GET", "/api/http-server/status")
    check("status 运行中", d["data"]["running"] is True and d["data"]["port"] == HTTP_PORT, d["data"]["port"])
    check("status 含 url", any(a.get("url", "").startswith("http://") for a in d["data"]["addresses"]),
          d["data"]["addresses"])

    # WebSocket 实时推送
    got = asyncio.run(ws_flow(sid))
    check("WS 实时收到 /ws-live", "/ws-live" in got, list(got.keys()))
    check("WS 实时收到 /ws-second", "/ws-second" in got, list(got.keys()))
    if "/ws-live" in got:
        rec = got["/ws-live"]
        check("WS 记录 query", rec["query"] == "from=ws", rec["query"])
        check("WS 记录 body", rec["body"] == '{"k":"v"}', rec["body"])

    # REST 回读
    st, d = api("GET", "/api/http-server/requests")
    check("REST requests 回读", d["data"]["count"] >= 2, d["data"]["count"])

    # 响应配置 REST
    st, d = api("POST", "/api/http-server/response", {"echo": False, "code": 418, "body": "teapot"})
    check("REST 更新响应配置", d["success"], d)
    st, body = hit("POST", "/teapot", b"ignored")
    check("REST 配置生效(418)", st == 418 and body == b"teapot", (st, body))
    api("POST", "/api/http-server/response", {"echo": True, "code": 200})

    # 清空
    st, d = api("POST", "/api/http-server/clear")
    check("REST 清空记录", d["success"], d)
    st, d = api("GET", "/api/http-server/requests")
    check("清空后为空", d["data"]["count"] == 0, d["data"]["count"])

    # 停止
    st, d = api("POST", "/api/http-server/stop")
    check("REST 停止服务", d["success"], d)
    st, d = api("GET", "/api/http-server/status")
    check("停止后 running=False", d["data"]["running"] is False, d["data"]["running"])

    # 停止后原端口不可访问
    try:
        hit("GET", "/after-stop")
        check("停止后 HTTP 端口拒绝", False, "仍可访问")
    except Exception:
        check("停止后 HTTP 端口拒绝", True)

    # 未启动时 requests 为空但不报错
    st, d = api("GET", "/api/http-server/requests")
    check("停止后 requests 接口正常", st == 200 and d["success"], d)
finally:
    try:
        api("POST", "/api/http-server/stop")
    except Exception:
        pass
    proc.terminate()
    try:
        proc.wait(timeout=10)
    except Exception:
        proc.kill()

print("\n==== 汇总: %d/%d ====" % (sum(1 for _, ok, _ in results if ok), len(results)))
failed = [n for n, ok, _ in results if not ok]
if failed:
    print("失败项: " + ", ".join(failed))
    sys.exit(1)
