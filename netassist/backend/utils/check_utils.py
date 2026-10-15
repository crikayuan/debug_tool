"""
校验算法工具
支持：校验和 Sum、异或 XOR、LRC、CRC16 (Modbus)、FCS (CRC16-CCITT-FALSE)
"""

from typing import Tuple


def checksum_sum(data: bytes) -> int:
    """校验和：所有字节累加取低 8 位"""
    return sum(data) & 0xFF


def checksum_xor(data: bytes) -> int:
    """异或校验：所有字节逐位异或"""
    result = 0
    for b in data:
        result ^= b
    return result & 0xFF


def checksum_lrc(data: bytes) -> int:
    """LRC 纵向冗余校验：累加取反 + 1，取低 8 位（Modbus ASCII 用）"""
    return (-sum(data)) & 0xFF


def crc16_modbus(data: bytes) -> int:
    """CRC16-Modbus：多项式 0xA001，初始值 0xFFFF"""
    crc = 0xFFFF
    for b in data:
        crc ^= b
        for _ in range(8):
            if crc & 0x0001:
                crc = (crc >> 1) ^ 0xA001
            else:
                crc >>= 1
    return crc & 0xFFFF


def crc16_ccitt(data: bytes) -> int:
    """CRC16-CCITT-FALSE：多项式 0x1021，初始值 0xFFFF"""
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF
    return crc & 0xFFFF


ALGORITHMS = {
    "sum": checksum_sum,
    "xor": checksum_xor,
    "lrc": checksum_lrc,
    "crc16": crc16_modbus,
    "fcs": crc16_ccitt,
}


def compute_check(algorithm: str, data: bytes) -> bytes:
    """
    计算校验值并返回追加字节。

    字节序约定：
    - sum / xor / lrc：单字节
    - crc16：低字节在前（Modbus 惯例）
    - fcs：高字节在前（CCITT/HDLC 惯例）
    """
    fn = ALGORITHMS.get(algorithm)
    if fn is None:
        raise ValueError(f"不支持的校验算法: {algorithm}")

    value = fn(data)
    if algorithm in ("sum", "xor", "lrc"):
        return bytes([value])
    elif algorithm == "crc16":
        return bytes([value & 0xFF, (value >> 8) & 0xFF])
    else:  # fcs
        return bytes([(value >> 8) & 0xFF, value & 0xFF])


def compute_check_hex(algorithm: str, data: bytes) -> str:
    """返回校验值的十六进制字符串（大写，带空格）"""
    return compute_check(algorithm, data).hex(" ").upper()
