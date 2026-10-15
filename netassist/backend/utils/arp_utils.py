"""
Windows ARP 表读取工具（网络扫描模块）。

通过 ctypes 调用 ``iphlpapi.GetIpNetTable`` 读取本机 IPv4 ARP 缓存，
返回 ``{ip: mac}`` 映射，MAC 统一格式为 ``AA:BB:CC:DD:EE:FF``（大写）。

结构体 ``MIB_IPNETROW`` 的字段偏移已在 Windows 上实测验证：
``dwIndex``(0) / ``dwPhysAddrLen``(4) / ``bPhysAddr``(8, CHAR[8]) /
``dwAddr``(16) / ``dwType``(20)，``sizeof == 24``。

注意：本项目在 ``netif_utils.py`` 上曾因结构体字段长度写错导致整体偏移，
此处严格采用已验证的定义，不做改动。读取后仅保留有效单播记录。
"""

import ctypes
import socket
import struct
import sys
from ctypes import wintypes
from typing import Dict

# 过滤规则：物理地址长度必须为 6（过滤多播/无效项的 0 长度）
_MAC_LEN: int = 6
# 多播 / 广播 / 未指定 段的首字节（这些地址不会出现在有效单播 ARP 记录中）
_IGNORED_FIRST_OCTETS = frozenset((0, 224, 225, 226, 227, 228, 229, 230,
                                   231, 232, 233, 234, 235, 236, 237, 238,
                                   239, 255))
# 子网广播记录的 MAC 固定为全 FF，需一并过滤
_BROADCAST_MAC = b"\xff" * _MAC_LEN


class MIB_IPNETROW(ctypes.Structure):
    """MIB_IPNETROW 结构体（字段偏移已实测验证，sizeof == 24）"""

    _fields_ = [
        ("dwIndex", wintypes.DWORD),         # offset 0  接口索引
        ("dwPhysAddrLen", wintypes.DWORD),   # offset 4  物理地址长度
        ("bPhysAddr", ctypes.c_ubyte * 8),   # offset 8  MAC（CHAR[8]）
        ("dwAddr", wintypes.DWORD),          # offset 16 IPv4（小端 uint32）
        ("dwType", wintypes.DWORD),          # offset 20 记录类型
    ]


def format_mac(mac_bytes: bytes) -> str:
    """将字节序列格式化为大写冒号分隔 MAC：b'\\xAA..' → 'AA:BB:CC:DD:EE:FF'"""
    return ":".join(f"{b:02X}" for b in mac_bytes)


def _is_ignored_ip(ip: str) -> bool:
    """判断 IP 是否属于需过滤的多播/广播/未指定段"""
    try:
        first = int(ip.split(".", 1)[0])
    except (ValueError, IndexError):
        return True
    return first in _IGNORED_FIRST_OCTETS


def get_arp_table() -> Dict[str, str]:
    """
    读取本机 IPv4 ARP 缓存。

    Returns:
        ``{ip: mac}`` 字典，MAC 为大写冒号分隔格式；非 Windows 或读取失败返回空字典。
    """
    if sys.platform != "win32":
        return {}

    try:
        iphlpapi = ctypes.windll.iphlpapi
    except Exception:
        return {}

    # 首次调用获取所需缓冲区大小（返回值通常为 ERROR_INSUFFICIENT_BUFFER = 122）
    size = wintypes.ULONG(0)
    try:
        iphlpapi.GetIpNetTable(None, ctypes.byref(size), False)
    except Exception:
        return {}

    if not size.value:
        return {}

    try:
        buf = ctypes.create_string_buffer(size.value)
        ret = iphlpapi.GetIpNetTable(buf, ctypes.byref(size), False)
    except Exception:
        return {}

    if ret != 0:
        return {}

    raw = buf.raw
    if len(raw) < 4:
        return {}

    try:
        num_entries = struct.unpack_from("<I", raw, 0)[0]
    except struct.error:
        return {}

    row_size = ctypes.sizeof(MIB_IPNETROW)
    table: Dict[str, str] = {}

    for index in range(num_entries):
        offset = 4 + index * row_size
        chunk = raw[offset:offset + row_size]
        if len(chunk) < row_size:
            break
        try:
            row = MIB_IPNETROW.from_buffer_copy(chunk)
        except Exception:
            continue

        # 过滤：非标准 MAC 长度（多播/无效项为 0）
        if row.dwPhysAddrLen != _MAC_LEN:
            continue

        mac_bytes = bytes(row.bPhysAddr[:_MAC_LEN])
        # 过滤：全零 MAC（无效项）与全 FF MAC（子网广播项）
        if mac_bytes == b"\x00" * _MAC_LEN or mac_bytes == _BROADCAST_MAC:
            continue

        ip = socket.inet_ntoa(struct.pack("<I", row.dwAddr & 0xFFFFFFFF))
        # 过滤：多播/广播/未指定段
        if _is_ignored_ip(ip):
            continue

        table[ip] = format_mac(mac_bytes)

    return table


if __name__ == "__main__":
    # 手动自测入口：打印读到的 IP-MAC 对，可与 `arp -a` 输出核对
    arp_table = get_arp_table()
    print(f"共读取 {len(arp_table)} 条有效 ARP 记录：")
    for ip, mac in sorted(arp_table.items(), key=lambda kv: tuple(int(x) for x in kv[0].split("."))):
        print(f"  {ip:<16} {mac}")
