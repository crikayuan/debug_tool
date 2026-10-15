"""
网卡分类与本机 IPv4 排序工具。

排序规则（用户要求）：有线网 IP → 无线网 IP → 虚拟网卡 IP → 回环 IP → 其他
Windows 下通过 GetAdaptersAddresses 读取 IANA 网卡类型，失败时回退到名称关键字判断。
"""
import ctypes
import socket
import sys
from ctypes import wintypes

# IANA ifType
IF_TYPE_ETHERNET = 6
IF_TYPE_PPP = 23
IF_TYPE_SOFTWARE_LOOPBACK = 24
IF_TYPE_PROP_VIRTUAL = 53
IF_TYPE_IEEE80211 = 71
IF_TYPE_TUNNEL = 131

# 分类优先级：数字越小越靠前
RANK_WIRED = 0
RANK_WIRELESS = 1
RANK_VIRTUAL = 2
RANK_LOOPBACK = 3
RANK_OTHER = 4

RANK_LABELS = {
    RANK_WIRED: "有线",
    RANK_WIRELESS: "无线",
    RANK_VIRTUAL: "虚拟",
    RANK_LOOPBACK: "回环",
    RANK_OTHER: "其他",
}

# 虚拟网卡关键字（命中即判定为虚拟，优先级高于有线/无线）
VIRTUAL_KEYWORDS = (
    "virtual", "vmware", "vmnet", "virtualbox", "hyper-v", "vethernet",
    "wsl", "docker", "tap-", "tun-", "tunnel", "teredo", "isatap",
    "pseudo", "sangfor", "easyconnect", "fortinet", "anyconnect",
    "zerotier", "hamachi", "radmin", "npcap", "vpn",
)

WIRELESS_KEYWORDS = (
    "wi-fi", "wifi", "wlan", "wireless", "无线", "802.11",
)

WIRED_KEYWORDS = (
    "ethernet", "以太网", "local area connection", "eth", "gbic", "lan",
)


class _IP_ADAPTER_ADDRESSES(ctypes.Structure):
    """IP_ADAPTER_ADDRESSES 前段结构（只需读取到 IfType）"""
    pass


_IP_ADAPTER_ADDRESSES._fields_ = [
    ("Length", wintypes.ULONG),
    ("IfIndex", wintypes.DWORD),
    ("Next", ctypes.POINTER(_IP_ADAPTER_ADDRESSES)),
    ("AdapterName", ctypes.c_char_p),
    ("FirstUnicastAddress", ctypes.c_void_p),
    ("FirstAnycastAddress", ctypes.c_void_p),
    ("FirstMulticastAddress", ctypes.c_void_p),
    ("FirstDnsServerAddress", ctypes.c_void_p),
    ("DnsSuffix", ctypes.c_wchar_p),
    ("Description", ctypes.c_wchar_p),
    ("FriendlyName", ctypes.c_wchar_p),
    # 注意：PhysicalAddress 是 CHAR[8]（8 字节，不是 WCHAR[8]），
    # 按 16 字节算会让后续 Length/Flags/Mtu/IfType 整体错位 +4
    ("PhysicalAddress", ctypes.c_ubyte * 8),
    ("PhysicalAddressLength", wintypes.ULONG),
    ("Flags", wintypes.ULONG),
    ("Mtu", wintypes.ULONG),
    ("IfType", wintypes.ULONG),
    ("OperStatus", wintypes.ULONG),
]


def _windows_iface_types():
    """
    读取 Windows 网卡类型表。

    Returns:
        dict: {网卡友好名称(小写): (ifType, 描述(小写))}，失败返回空字典
    """
    if sys.platform != "win32":
        return {}
    try:
        iphlpapi = ctypes.windll.iphlpapi
        af_inet = wintypes.ULONG(socket.AF_INET)
        zero = wintypes.ULONG(0)

        size = wintypes.ULONG(0)
        ret = iphlpapi.GetAdaptersAddresses(af_inet, zero, None, None, ctypes.byref(size))
        if ret != 0 and ret != 111:  # 111 = ERROR_BUFFER_OVERFLOW
            return {}

        buf = ctypes.create_string_buffer(max(size.value, 16384))
        addr = ctypes.cast(buf, ctypes.POINTER(_IP_ADAPTER_ADDRESSES))
        ret = iphlpapi.GetAdaptersAddresses(af_inet, zero, None, addr, ctypes.byref(size))
        if ret != 0:
            return {}

        table = {}
        node = addr
        for _ in range(256):
            if not node:
                break
            cur = node.contents
            name = (cur.FriendlyName or "").lower()
            desc = (cur.Description or "").lower()
            if name:
                table[name] = (int(cur.IfType), desc)
            if not cur.Next:
                break
            node = cur.Next
        return table
    except Exception:
        return {}


def _ip_sort_key(ip):
    """IPv4 数值排序键，非法地址排最后"""
    try:
        return (0, tuple(int(x) for x in ip.split(".")))
    except Exception:
        return (1, (999, 999, 999, 999))


def classify_interface(iface_name, iftype=None, description=""):
    """
    判定网卡类别，返回 RANK_* 常量。
    判断顺序：回环 → 虚拟（关键字/ifType） → 无线 → 有线 → 其他
    """
    name = (iface_name or "").lower()
    desc = (description or "").lower()
    text = f"{name} {desc}"

    if iftype == IF_TYPE_SOFTWARE_LOOPBACK or "loopback" in text:
        return RANK_LOOPBACK

    if any(k in text for k in VIRTUAL_KEYWORDS):
        return RANK_VIRTUAL
    if iftype in (IF_TYPE_PROP_VIRTUAL, IF_TYPE_TUNNEL):
        return RANK_VIRTUAL

    if iftype == IF_TYPE_IEEE80211 or any(k in text for k in WIRELESS_KEYWORDS):
        return RANK_WIRELESS

    if iftype in (IF_TYPE_ETHERNET, IF_TYPE_PPP) or any(k in text for k in WIRED_KEYWORDS):
        return RANK_WIRED

    return RANK_OTHER


def classify_ip(iface_name, ip, iftype=None, description=""):
    """按网卡类别判定 IP 归属；回环地址强制归到回环组"""
    if ip.startswith("127."):
        return RANK_LOOPBACK
    return classify_interface(iface_name, iftype, description)


def sort_local_ips(entries):
    """
    对本机 IPv4 条目排序。

    Args:
        entries: [(ip, rank)] 列表

    Returns:
        按 rank → IP 数值 排序后的 ip 列表
    """
    return [ip for ip, _ in sorted(entries, key=lambda e: (e[1], _ip_sort_key(e[0])))]
