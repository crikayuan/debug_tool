# -*- coding: utf-8 -*-
"""HTTP Server 模块后端自测（直接调 manager，不经 FastAPI）。"""
import sys
import time
import json
import http.client

sys.path.insert(0, r"D:\workbuddy\2026-10-10-14-59-54\netassist\backend")

from models import HttpServerConfig, HttpResponseConfig
from services.http_server_service import http_server_manager

PORT = 18080
results = []


def check(name, ok, detail=""):
    results.append((name, ok, detail))
    print(("PASS " if ok else "FAIL ") + name + (("  -> " + str(detail)) if detail else ""))


def req(method, path, body=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", PORT, timeout=5)
    conn.request(method, path, body=body, headers=headers or {})
    resp = conn.getresponse()
    data = resp.read()
    st = resp.status
    hdrs = dict(resp.getheaders())
    conn.close()
    return st, hdrs, data


# 1. 启动
cfg = HttpServerConfig(port=PORT, bind="127.0.0.1", response=HttpResponseConfig(echo=True))
r = http_server_manager.start(cfg)
check("启动服务", r.success, r.message)
if not r.success:
    sys.exit(1)
sid = r.data["session_id"]
check("返回 session_id", bool(sid))
check("返回访问地址列表", len(r.data.get("addresses", [])) > 0, r.data.get("addresses"))

# 2. POST + echo 回显
payload = json.dumps({"hello": "码头", "n": 1}, ensure_ascii=False).encode("utf-8")
st, hdrs, data = req("POST", "/api/test?a=1&b=2", payload, {"Content-Type": "application/json"})
check("POST 状态码 200", st == 200, st)
check("echo 回显字节一致", data == payload, data[:80])
check("echo 保留 Content-Type", "application/json" in hdrs.get("Content-Type", ""), hdrs.get("Content-Type"))
check("Content-Length 正确", hdrs.get("Content-Length") == str(len(payload)), hdrs.get("Content-Length"))

# 3. 记录内容
time.sleep(0.2)
records = http_server_manager.get_records()
check("记录已入队", len(records) >= 1, len(records))
rec = records[-1]
check("记录 method", rec["method"] == "POST", rec["method"])
check("记录 path", rec["path"] == "/api/test", rec["path"])
check("记录 query", rec["query"] == "a=1&b=2", rec["query"])
check("记录 client_ip", rec["client_ip"] == "127.0.0.1", rec["client_ip"])
check("记录 body 文本", "码头" in rec["body"], rec["body"])
check("记录 body_size", rec["body_size"] == len(payload), rec["body_size"])
check("记录 headers", rec["headers"].get("Content-Type") == "application/json", rec["headers"])

# 4. 各方法
for m in ("GET", "PUT", "DELETE", "PATCH", "OPTIONS"):
    st, hdrs, data = req(m, "/m/" + m)
    check("方法 %s 接收" % m, st == 200, st)

# 5. HEAD（无正文但 Content-Length 正确）
st, hdrs, data = req("HEAD", "/head-test")
check("HEAD 状态码", st == 200, st)
check("HEAD 无正文", data == b"", data)

# 6. 二进制 body → HEX
binary = bytes([0x00, 0x01, 0xFF, 0xAB, 0xCD, 0x7F])
st, hdrs, data = req("POST", "/bin", binary, {"Content-Type": "application/octet-stream"})
check("二进制 echo 字节一致", data == binary, data)
time.sleep(0.15)
rec = http_server_manager.get_records()[-1]
check("二进制标记 is_binary", rec["is_binary"] is True, rec["is_binary"])
check("二进制 HEX 正确", rec["body_hex"] == "00 01 FF AB CD 7F", rec["body_hex"])
check("二进制 body 为空", rec["body"] == "", rec["body"])

# 7. 自定义响应（echo=False）
r2 = http_server_manager.set_response_config(
    {"echo": False, "code": 201, "content_type": "text/plain; charset=utf-8", "body": "OK-自定义"}
)
check("更新响应配置", r2.success, r2.message)
st, hdrs, data = req("POST", "/custom", b"ignored")
check("自定义状态码 201", st == 201, st)
check("自定义响应体", data.decode("utf-8") == "OK-自定义", data)
check("自定义 Content-Type", "text/plain" in hdrs.get("Content-Type", ""), hdrs.get("Content-Type"))

# 8. 延迟
http_server_manager.set_response_config({"echo": True, "code": 200})
t0 = time.time()
st, hdrs, data = req("POST", "/delay", b"x")
check("无延迟 < 0.5s", (time.time() - t0) < 0.5, "%.3f" % (time.time() - t0))
http_server_manager.set_response_config({"delay_ms": 800})
t0 = time.time()
st, hdrs, data = req("POST", "/delay2", b"x")
elapsed = time.time() - t0
check("800ms 延迟生效", elapsed >= 0.75, "%.3f" % elapsed)
http_server_manager.set_response_config({"delay_ms": 0})

# 9. 中文 / 特殊路径（URL 中路径必须百分号编码，客户端行为）
st, hdrs, data = req("GET", "/%E4%B8%AD%E6%96%87/%E8%B7%AF%E5%BE%84?q=%E4%B8%AD")
check("中文路径接收", st == 200, st)
time.sleep(0.15)
rec = http_server_manager.get_records()[-1]
check(
    "中文路径记录",
    rec["raw_path"].startswith("/%E4%B8%AD%E6%96%87"),
    rec["raw_path"],
)

# 10. 大 body（1MB）
big = b"A" * (1024 * 1024)
st, hdrs, data = req("POST", "/big", big)
check("1MB body echo 一致", data == big, len(data))

# 11. 队列消费
consumed = 0
while http_server_manager.read_event() is not None:
    consumed += 1
    if consumed > 10000:
        break
check("队列可消费", consumed > 5, consumed)
check("队列已排空", http_server_manager.read_event() is None)

# 12. 清空
r3 = http_server_manager.clear()
check("清空记录", r3.success and len(http_server_manager.get_records()) == 0, r3.message)

# 13. status
stt = http_server_manager.status()
check("status running", stt["running"] is True)
check("status port", stt["port"] == PORT, stt["port"])
check("status session_id", stt["session_id"] == sid)
check("status addresses 含 url", any(a.get("url", "").startswith("http://") for a in stt["addresses"]), stt["addresses"])

# 14. 重复启动应失败
r4 = http_server_manager.start(cfg)
check("重复启动被拒", not r4.success, r4.message)

# 15. 保留端口段被拒
http_server_manager.stop()
r5 = http_server_manager.start(HttpServerConfig(port=20010, bind="127.0.0.1"))
check("保留端口段被拒", not r5.success, r5.message)

# 16. 端口占用检测
import socket as _s
occ = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
occ.bind(("127.0.0.1", PORT))
occ.listen(1)
r6 = http_server_manager.start(HttpServerConfig(port=PORT, bind="127.0.0.1"))
check("占用端口被拒", not r6.success, r6.message)
occ.close()

# 17. 停止 + 端口释放
r7 = http_server_manager.start(HttpServerConfig(port=PORT, bind="127.0.0.1"))
check("重新启动成功", r7.success, r7.message)
r8 = http_server_manager.stop()
check("停止成功", r8.success, r8.message)
check("停止后 is_running=False", http_server_manager.is_running() is False)
time.sleep(0.3)
try:
    probe = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    probe.bind(("127.0.0.1", PORT))
    probe.close()
    check("端口已释放", True)
except OSError as e:
    check("端口已释放", False, e)

# 18. 停止后可重新启动
r9 = http_server_manager.start(HttpServerConfig(port=PORT, bind="127.0.0.1"))
check("停止后可重启", r9.success, r9.message)
http_server_manager.stop()

# 19. 导出
http_server_manager.start(HttpServerConfig(port=PORT, bind="127.0.0.1"))
req("POST", "/export-test", b"export-body")
time.sleep(0.2)
from services.http_server_service import export_records
info = export_records(http_server_manager.get_records(), r"D:\workbuddy\2026-10-10-14-59-54\netassist\tests", "http_selftest.txt")
check("导出文件", info["count"] >= 1 and info["size"] > 0, info)
with open(info["path"], "r", encoding="utf-8-sig") as f:
    text = f.read()
check("导出内容含请求", "/export-test" in text and "export-body" in text)
http_server_manager.stop()

print("\n==== 汇总: %d/%d ====" % (sum(1 for _, ok, _ in results if ok), len(results)))
failed = [n for n, ok, _ in results if not ok]
if failed:
    print("失败项: " + ", ".join(failed))
    sys.exit(1)
