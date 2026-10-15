# -*- coding: utf-8 -*-
"""QA 独立单元测试：ip_range_utils / vendor_utils / arp_utils / scan_service 原子操作。

运行： <netassist python> tests/_qa_tmp/test_unit_scan.py
"""
import os
import sys
import time
import socket
import threading

HERE = os.path.dirname(os.path.abspath(__file__))
BACKEND = os.path.normpath(os.path.join(HERE, "..", "backend"))
sys.path.insert(0, BACKEND)

from utils import ip_range_utils as ipu
from utils import vendor_utils as vu
from utils import arp_utils as au
from services.scan_service import ScanManager, export_csv

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"  [{'PASS' if cond else 'FAIL'}] {name}" + (f" — {detail}" if detail else ""))


def expect_value_error(fn, name):
    try:
        fn()
        check(name, False, "未抛错")
    except ValueError as e:
        check(name, True, f"ValueError: {e}")
    except Exception as e:
        check(name, False, f"抛出了非 ValueError: {type(e).__name__}: {e}")


print("== 1. ip_range_utils 解析 ==")
r = ipu.parse_scan_range("192.168.1.1-254")
check("简写 1-254 -> 254 个", len(r) == 254 and r[0] == "192.168.1.1" and r[-1] == "192.168.1.254",
      f"len={len(r)} head={r[0]} tail={r[-1]}")

r = ipu.parse_scan_range("192.168.1.0/24")
check("CIDR /24 -> 254 个 (.1~.254)",
      len(r) == 254 and r[0] == "192.168.1.1" and r[-1] == "192.168.1.254",
      f"len={len(r)} head={r[0]} tail={r[-1]}")

r = ipu.parse_scan_range("192.168.1.10", "192.168.1.13")
check("起止 IP 闭区间 -> 4 个", r == ["192.168.1.10", "192.168.1.11", "192.168.1.12", "192.168.1.13"], str(r))

r = ipu.parse_scan_range("10.0.0.10")
check("单个 IP -> 1 个", r == ["10.0.0.10"], str(r))

r = ipu.parse_scan_range("192.168.1.5-192.168.1.8")
check("完整双 IP 范围 -> 4 个", len(r) == 4 and r[0] == "192.168.1.5" and r[-1] == "192.168.1.8", str(r))

# /30 边界
r = ipu.parse_scan_range("192.168.1.0/30")
check("/30 -> 2 主机 (.1 .2)", r == ["192.168.1.1", "192.168.1.2"], str(r))

r = ipu.parse_scan_range("192.168.1.1/32")
check("/32 -> 1 地址", r == ["192.168.1.1"], str(r))

# 非法输入
expect_value_error(lambda: ipu.parse_scan_range(""), "空范围 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("abc"), "非 IP 字符串 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.300"), "越界 IP -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.1-300"), "简写结束段 300 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.254-100"), "起 > 止 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.5", "192.168.1.1"), "起止倒置 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.1-"), "缺结束 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.0/33"), "非法掩码 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("1.2.3.4.5"), "五段 IP -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.1", "not-an-ip"), "end 非法 -> ValueError")
expect_value_error(lambda: ipu.parse_scan_range("999.1.1.1"), "首段越界 -> ValueError")

# 跨网段
r = ipu.parse_scan_range("192.168.1.250", "192.168.2.5")
check("跨网段落段范围可用 -> 12 个", len(r) == 12 and r[0] == "192.168.1.250" and r[-1] == "192.168.2.5",
      f"len={len(r)}")

# 超大范围 & 上限保护（含耗时观测，防止先物化再判超限导致卡顿）
t0 = time.perf_counter()
expect_value_error(lambda: ipu.parse_scan_range("10.0.0.0/8"), "10.0.0.0/8 超限 -> ValueError")
dt8 = time.perf_counter() - t0
print(f"       (/8 拒绝耗时 {dt8*1000:.1f} ms)")

t0 = time.perf_counter()
expect_value_error(lambda: ipu.parse_scan_range("10.0.0.0/16", "10.1.0.0") if False else ipu.parse_scan_range("10.0.0.0/15"),
                   "10.0.0.0/15 超限 -> ValueError")
dt15 = time.perf_counter() - t0
print(f"       (/15 拒绝耗时 {dt15*1000:.1f} ms)")

# /16 = 65534 恰好 <= 65536，应被接受（边界内）
t0 = time.perf_counter()
r16 = ipu.parse_scan_range("10.0.0.0/16")
dt16 = time.perf_counter() - t0
check("/16 = 65534 边界内被接受", len(r16) == 65534, f"len={len(r16)} 耗时 {dt16*1000:.0f}ms")

# 上限边界：max_hosts 参数
expect_value_error(lambda: ipu.parse_scan_range("192.168.1.1", "192.168.1.20", max_hosts=10),
                   "自定义 max_hosts=10 时 20 个地址超限")

print("\n== 2. vendor_utils OUI 查表 ==")
print(f"   oui 路径: {vu.resolve_oui_path()}")
check("OUI 表已加载且条目数合理", vu.table_size() > 30000, f"size={vu.table_size()}")

# 从文件里取真实 OUI 对照
samples = {
    "3C:5A:B4:11:22:33": "Google, Inc.",
    "E0:50:8B:11:22:04": "Zhejiang Dahua Technology Co., Ltd.",
    "A4:2B:B0:11:22:33": "TP-LINK TECHNOLOGIES CO.,LTD.",
}
for mac, want in samples.items():
    got = vu.lookup_vendor(mac)
    check(f"查表 {mac} -> {want!r}", got == want, f"实际 {got!r}")

# 归一化：不同分隔符/小写/无分隔
for form in ["3c5ab4112233", "3C-5A-B4-11-22-33", "3c:5a:b4:11:22:33"]:
    check(f"归一化 {form}", vu.lookup_vendor(form) == "Google, Inc.", f"实际 {vu.lookup_vendor(form)!r}")

# 未命中 / 非法
check("未命中 OUI -> 空串", vu.lookup_vendor("FF:FF:FF:00:00:00") == "", f"实际 {vu.lookup_vendor('FF:FF:FF:00:00:00')!r}")
check("MAC 过短 -> 空串", vu.lookup_vendor("AA:BB") == "", f"实际 {vu.lookup_vendor('AA:BB')!r}")
check("空 MAC -> 空串", vu.lookup_vendor("") == "")
check("含非法字符 -> 空串", vu.lookup_vendor("ZZ:ZZ:ZZ:ZZ:ZZ:ZZ") == "")

print("\n== 3. arp_utils 读取与过滤 ==")
tbl = au.get_arp_table()
check("ARP 表读取非空", len(tbl) > 0, f"count={len(tbl)}")
bad = [ip for ip in tbl if ip.split(".")[0] in ("224", "239", "255", "0")]
check("已过滤多播/广播段", not bad, f"异常项={bad}")
mac_bad = [ip for ip, m in tbl.items() if m in ("FF:FF:FF:FF:FF:FF", "00:00:00:00:00:00")]
check("已过滤全 FF / 全 00 MAC", not mac_bad, f"异常项={mac_bad}")
fmt_bad = [m for m in tbl.values() if len(m) != 17]
check("MAC 格式均为 AA:BB:.. (17 字符)", not fmt_bad, f"异常={fmt_bad[:3]}")

print("\n== 4. scan_service 原子操作 ==")
sm = ScanManager()
check("_clamp_int 下界", sm._clamp_int(1, 128, 8, 512) == 8)
check("_clamp_int 上界", sm._clamp_int(9999, 128, 8, 512) == 512)
check("_clamp_int 非法取默认", sm._clamp_int("x", 128, 8, 512) == 128)
check("_resolve_probe_ports 关闭端口探测->默认", sm._resolve_probe_ports({"port_scan": False, "ports": [502]}) == [80, 443, 22, 445, 3389])
check("_resolve_probe_ports 开启->用传入", sm._resolve_probe_ports({"port_scan": True, "ports": [502, 102, "44818", 70000, 0]}) == [502, 102, 44818])
check("_resolve_probe_ports 去重", sm._resolve_probe_ports({"port_scan": True, "ports": [80, 80, 443]}) == [80, 443])

# TCP 探测语义：本地开一个监听端口 -> open；关闭端口 -> refused(在线)；黑洞地址 -> down
srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
srv.bind(("127.0.0.1", 0))
srv.listen(5)
open_port = srv.getsockname()[1]
t = threading.Thread(target=lambda: [srv.accept()[0].close() for _ in range(5)], daemon=True)
t.start()

st, d = ScanManager._tcp_probe("127.0.0.1", open_port, 0.5)
check("开放端口 -> open", st == "open", f"status={st} delay={d:.4f}")

st2, _ = ScanManager._tcp_probe("127.0.0.1", 59999, 0.4)  # 本机无监听端口
# 环境说明：本机（含回环）关闭端口不回 RST，而是被丢弃 -> 超时 10035，故此处为 down，
# refused 分支无法在真实网络上触发（详见测试报告「环境相关」），改为注入验证语义。
check("关闭端口在本机表现为 down(环境: 不回 RST)", st2 in ("down", "refused"), f"status={st2}")

st3, _ = ScanManager._tcp_probe("192.0.2.1", 9, 0.15)  # TEST-NET-1 黑洞
check("黑洞地址 -> down", st3 == "down", f"status={st3}")

# _probe_ip 组合语义
pr = sm._probe_ip("127.0.0.1", [open_port], 0.5, False, threading.Event())
check("_probe_ip 开放端口 online=True, 含端口", pr["online"] and pr["ports"] == [open_port], str(pr))

# 注入 refused 返回值，独立验证「被拒=在线」语义（不依赖真实网络是否回 RST）
_orig_probe = ScanManager._tcp_probe
ScanManager._tcp_probe = staticmethod(lambda ip, port, to: ("refused", 0.01))
try:
    pr_ref = sm._probe_ip("10.9.9.9", [22], 0.3, False, threading.Event())
    check("注入 refused -> _probe_ip 判 online 且无开放端口",
          pr_ref["online"] and pr_ref["ports"] == [], str(pr_ref))
    pr_ref_all = sm._probe_ip("10.9.9.9", [22], 0.3, True, threading.Event())
    check("注入 refused(开端口探测) -> online 且端口不计入开放",
          pr_ref_all["online"] and pr_ref_all["ports"] == [], str(pr_ref_all))
finally:
    ScanManager._tcp_probe = staticmethod(_orig_probe)
check("_REFUSED_CODES 覆盖 10061/10054/111/104",
      {10061, 10054, 111, 104} <= set(__import__("services.scan_service", fromlist=["x"])._REFUSED_CODES))

pr2 = sm._probe_ip("192.0.2.1", [9], 0.15, False, threading.Event())
check("_probe_ip 仅超时仍判离线", pr2["online"] is False, str(pr2))
ev = threading.Event(); ev.set()
check("_probe_ip 已停止返回 None", sm._probe_ip("127.0.0.1", [open_port], 0.5, False, ev) is None)

# 停止标志在端口遍历中生效
ev2 = threading.Event(); ev2.set()
check("停止标志优先级", sm._probe_ip("127.0.0.1", [open_port], 0.5, True, ev2) is None)

srv.close()

print("\n== 5. CSV 导出 ==")
out_dir = os.path.join(HERE, "_out")
items = [
    {"ip": "192.168.1.7", "mac": "3C:5A:B4:CC:DD:02", "vendor": "Google, Inc.", "hostname": "plc-a03",
     "delay_ms": 3, "ports": [502, 102], "online": True, "note": "3号泊位PLC"},
    {"ip": "192.168.1.9", "mac": "", "vendor": "", "hostname": "", "delay_ms": 0, "ports": [], "online": False, "note": ""},
]
info = export_csv(items, out_dir, "qa_scan.csv")
check("CSV 文件生成", os.path.exists(info["path"]) and info["count"] == 2, str(info))
with open(info["path"], "rb") as f:
    head = f.read(3)
check("CSV 带 UTF-8 BOM", head == b"\xef\xbb\xbf", f"head={head!r}")
with open(info["path"], "r", encoding="utf-8-sig") as f:
    content = f.read()
check("CSV 含表头与备注", "IP 地址" in content and "3号泊位PLC" in content)

print("\n===== 单元测试汇总 =====")
print(f"  PASS {len(PASS)} / {len(PASS)+len(FAIL)}")
if FAIL:
    print("  失败项:")
    for f in FAIL:
        print("   -", f)
sys.exit(1 if FAIL else 0)
