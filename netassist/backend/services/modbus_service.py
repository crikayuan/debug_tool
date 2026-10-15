"""
Modbus 帧拼装服务
支持 RTU / TCP / ASCII 三种协议，常用功能码
"""

import struct

from utils.check_utils import crc16_modbus, checksum_lrc

READ_FUNCTIONS = {1, 2, 3, 4}


def _int16(v: int) -> bytes:
    return struct.pack(">H", v & 0xFFFF)


def _pack_reg(v: int, byte_order: str = "big") -> bytes:
    v &= 0xFFFF
    if byte_order == "little":
        return bytes([v & 0xFF, (v >> 8) & 0xFF])
    return bytes([(v >> 8) & 0xFF, v & 0xFF])


def _pack_coils(values) -> bytes:
    n = len(values)
    byte_count = (n + 7) // 8
    out = bytearray(byte_count)
    for i, v in enumerate(values):
        if v:
            out[i // 8] |= 1 << (i % 8)
    return bytes(out)


def _build_pdu(function, address, quantity, values, byte_order) -> bytes:
    if function in READ_FUNCTIONS:
        return bytes([function]) + _int16(address) + _int16(quantity)

    if function == 5:  # 写单个线圈
        val = 0xFF00 if (values and values[0]) else 0x0000
        return bytes([function]) + _int16(address) + _int16(val)

    if function == 6:  # 写单个寄存器
        v = values[0] if values else 0
        return bytes([function]) + _int16(address) + _pack_reg(v, byte_order)

    if function == 15:  # 写多个线圈 0x0F
        coils = _pack_coils(values[: max(1, quantity)])
        return (
            bytes([function])
            + _int16(address)
            + _int16(quantity)
            + bytes([len(coils)])
            + coils
        )

    if function == 16:  # 写多个寄存器 0x10
        regs = b"".join(
            _pack_reg(v, byte_order) for v in values[: max(1, quantity)]
        )
        return (
            bytes([function])
            + _int16(address)
            + _int16(quantity)
            + bytes([len(regs)])
            + regs
        )

    raise ValueError(f"不支持的功能码: 0x{function:02X}")


def build_modbus_frame(
    protocol: str = "rtu",
    slave_id: int = 1,
    function: int = 3,
    address: int = 0,
    quantity: int = 1,
    values=None,
    byte_order: str = "big",
) -> dict:
    """
    拼装 Modbus 帧。

    Returns:
        {"protocol", "frame_hex", "frame_bytes", "length"}
    """
    values = values or []
    pdu = _build_pdu(function, address, quantity, values, byte_order)

    if protocol == "rtu":
        frame = bytes([slave_id & 0xFF]) + pdu
        crc = crc16_modbus(frame)
        frame += bytes([crc & 0xFF, (crc >> 8) & 0xFF])

    elif protocol == "ascii":
        frame = bytes([slave_id & 0xFF]) + pdu
        lrc = checksum_lrc(frame)
        ascii_body = ":" + frame.hex().upper() + f"{lrc:02X}" + "\r\n"
        frame = ascii_body.encode("ascii")

    else:  # tcp
        length = 1 + len(pdu)
        mbap = struct.pack(">HHHB", 0, 0, length, slave_id & 0xFF)
        frame = mbap + pdu

    return {
        "protocol": protocol,
        "frame_hex": frame.hex(" ").upper(),
        "frame_bytes": frame,
        "length": len(frame),
    }
