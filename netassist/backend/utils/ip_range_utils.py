"""
IP 范围解析工具（网络扫描模块）。

支持三种常见写法（全部基于标准库 ``ipaddress``，零第三方依赖）：
1. 简写范围      ``192.168.1.1-254`` 或 ``192.168.1.1-192.168.1.100``
2. CIDR 网段     ``192.168.1.0/24``
3. 起止 IP       起始 ``192.168.1.1`` + 结束 ``192.168.1.100``
另外兼容单个 IP（视为起止相同）。

返回按 IPv4 数值自然升序排列的字符串列表；总地址数设有上限保护，
超限抛出 ``ValueError``（由上层路由转换为 400 明确错误，而非 500）。
"""

from typing import List

import ipaddress

# 单次扫描地址数量上限（含），避免误填超大网段导致线程池/内存爆炸
MAX_HOSTS: int = 65536


def parse_scan_range(start: str, end: str = "", max_hosts: int = MAX_HOSTS) -> List[str]:
    """
    解析扫描范围，返回有序 IPv4 字符串列表。

    Args:
        start: 起始表达式，可为 ``192.168.1.1`` / ``192.168.1.1-254`` /
            ``192.168.1.0/24`` / ``192.168.1.1-192.168.1.100``
        end: 结束 IP（与 ``start`` 组成起止范围）；为空时 ``start`` 单独解析
        max_hosts: 地址数量上限，超过则报错

    Returns:
        按数值自然升序的 IPv4 字符串列表

    Raises:
        ValueError: 表达式非法、起止倒置或数量超限
    """
    text = (start or "").strip()
    end_text = (end or "").strip()

    if not text:
        raise ValueError("扫描范围不能为空")

    # 情况一：显式起止 IP（start 与 end 均为完整 IP）
    if end_text:
        return _range_from_bounds(text, end_text, max_hosts)

    # 情况二：CIDR 网段
    if "/" in text:
        return _range_from_cidr(text, max_hosts)

    # 情况三：含 "-" 的简写/完整范围
    if "-" in text:
        left, _, right = text.partition("-")
        left = left.strip()
        right = right.strip()
        if not left or not right:
            raise ValueError(f"非法的范围写法: {text}")
        if "." not in right:
            # 简写：192.168.1.1-254 → 自动补全前 3 段
            if not right.isdigit() or not (0 <= int(right) <= 255):
                raise ValueError(f"非法的结束段: {text}")
            prefix = left.rsplit(".", 1)[0] if "." in left else ""
            if not prefix:
                raise ValueError(f"非法的范围写法: {text}")
            end_ip = f"{prefix}.{int(right)}"
        else:
            end_ip = right
        return _range_from_bounds(left, end_ip, max_hosts)

    # 情况四：单个 IP
    return _range_from_bounds(text, text, max_hosts)


def count_scan_range(start: str, end: str = "", max_hosts: int = MAX_HOSTS) -> int:
    """返回范围解析后的地址数量（供前端提示使用，行为与 parse_scan_range 一致）"""
    return len(parse_scan_range(start, end, max_hosts))


def _range_from_bounds(start_ip: str, end_ip: str, max_hosts: int) -> List[str]:
    """由起止 IP 生成列表（闭区间，含两端）"""
    try:
        start_addr = ipaddress.IPv4Address(start_ip)
        end_addr = ipaddress.IPv4Address(end_ip)
    except ValueError as exc:
        raise ValueError(f"非法 IP 地址: {start_ip} - {end_ip}（{exc}）") from exc

    start_int = int(start_addr)
    end_int = int(end_addr)
    if start_int > end_int:
        raise ValueError(f"起始 IP 不能大于结束 IP: {start_ip} > {end_ip}")

    total = end_int - start_int + 1
    if total > max_hosts:
        raise ValueError(f"扫描地址数量 {total} 超过上限 {max_hosts}")

    return [str(ipaddress.IPv4Address(value)) for value in range(start_int, end_int + 1)]


def _range_from_cidr(text: str, max_hosts: int) -> List[str]:
    """
    由 CIDR 生成可用主机地址列表。

    对于 /24 等常规网段，取 ``network.hosts()``（排除网络号与广播地址，共 254 个）；
    对于 /31、/32 等特殊网段，退化为枚举全部地址。
    """
    try:
        network = ipaddress.ip_network(text, strict=False)
    except ValueError as exc:
        raise ValueError(f"非法 CIDR 网段: {text}（{exc}）") from exc

    if not isinstance(network, ipaddress.IPv4Network):
        raise ValueError(f"仅支持 IPv4 网段: {text}")

    # 先按网络规模判断是否超限，再决定是否物化地址列表。
    # 否则 /8 这类超大网段会先生成上千万个元素才报错，既浪费内存，
    # 还会同步阻塞事件循环（实测 10.0.0.0/8 耗时近 10 秒，期间整个后端无响应）。
    host_count = (
        network.num_addresses - 2 if network.num_addresses > 2 else network.num_addresses
    )
    if host_count > max_hosts:
        raise ValueError(f"扫描地址数量 {host_count} 超过上限 {max_hosts}")

    if network.num_addresses > 2:
        hosts = list(network.hosts())
    else:
        hosts = list(network)

    return [str(host) for host in hosts]


if __name__ == "__main__":
    # 手动自测入口
    for expr, end in [
        ("192.168.1.1-254", ""),
        ("192.168.1.0/30", ""),
        ("192.168.1.1", "192.168.1.5"),
        ("10.0.0.10", ""),
    ]:
        result = parse_scan_range(expr, end)
        print(f"{expr!r} end={end!r} -> count={len(result)} head={result[:3]} tail={result[-3:]}")
