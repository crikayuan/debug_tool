"""
数据处理工具函数
编码支持 UTF-8 / GBK，格式支持 text / hex，发送支持结束符与自动校验
"""

import base64
from typing import Optional

from utils.check_utils import compute_check

ENCODINGS = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "gbk": "gbk",
    "gb2312": "gbk",
    "ansi": "gbk",
}


def _encode_text(data: str, encoding: str) -> bytes:
    """按指定编码将文本编码为字节，失败回退 UTF-8"""
    enc = ENCODINGS.get(encoding, "utf-8")
    try:
        return data.encode(enc)
    except Exception:
        return data.encode("utf-8", errors="ignore")


def _parse_hex_loose(data: str):
    """
    宽容解析十六进制字符串，不因长度或字符问题拒绝发送。

    规则（尽量可预测，不静默丢字符）：
    1. 去掉所有空白字符
    2. 只要出现非十六进制字符，就返回 None，由调用方按纯文本原样发送
    3. 奇数长度时在前面补 0（如 "1" -> 0x01、"ABC" -> 0x0A 0xBC）
    """
    cleaned = "".join(data.split())
    if not cleaned:
        return None
    if any(ch not in "0123456789abcdefABCDEF" for ch in cleaned):
        return None
    if len(cleaned) % 2 != 0:
        cleaned = "0" + cleaned
    try:
        return bytes.fromhex(cleaned)
    except ValueError:
        return None


def format_data_for_send(
    data: str,
    format_type: str = "text",
    encoding: str = "utf-8",
    end_chars: str = "",
    append_check: Optional[str] = None,
) -> bytes:
    """
    格式化要发送的数据。

    Args:
        data: 要发送的数据（长度、内容均不作限制，1 个字符也能发）
        format_type: 'text' 或 'hex'
        encoding: 文本编码 utf-8 / gbk
        end_chars: 结束符（控制字符，如 "\\r\\n"）
        append_check: 校验算法 sum/xor/lrc/crc16/fcs
    """
    if data is None:
        raise ValueError("数据不能为None")
    data = str(data)

    if format_type == "hex":
        payload = _parse_hex_loose(data)
        # 解析不出任何合法十六进制字节时，退回按文本编码发送，保证任何输入都能发出去
        if payload is None:
            payload = _encode_text(data, encoding)
    elif format_type in ("file", "base64"):
        # FILE 类型：前端把文件内容读成 base64 传上来，这里解码成原始字节
        try:
            payload = base64.b64decode(data, validate=True)
        except Exception:
            raise ValueError("文件内容不是有效的 base64 编码")
    else:
        payload = _encode_text(data, encoding)

    # 追加结束符（结束符为控制字符，统一按 latin-1 编码为字节）
    if end_chars:
        try:
            payload += end_chars.encode("latin-1")
        except Exception:
            pass

    # 自动附加校验
    if append_check:
        payload += compute_check(append_check, payload)

    return payload


def format_received_data(data: bytes, encoding: str = "utf-8") -> dict:
    """
    格式化接收到的数据。

    Returns:
        包含 text / hex / length 的字典
    """
    enc = ENCODINGS.get(encoding, "utf-8")
    try:
        text = data.decode(enc, errors="ignore")
    except Exception:
        text = data.decode("utf-8", errors="ignore")
    return {
        "text": text,
        "hex": data.hex(" ").upper(),
        "length": len(data),
    }


def validate_hex_string(hex_str: str) -> bool:
    """验证十六进制字符串格式"""
    try:
        bytes.fromhex(hex_str.replace(" ", ""))
        return True
    except ValueError:
        return False


def convert_hex_to_text(hex_str: str, encoding: str = "utf-8") -> str:
    """十六进制字符串转文本（奇数长度自动左补 0，不报错）"""
    cleaned = "".join(hex_str.split())
    if not cleaned:
        return ""
    if len(cleaned) % 2 != 0:
        cleaned = "0" + cleaned
    try:
        raw = bytes.fromhex(cleaned)
    except ValueError:
        return ""
    enc = ENCODINGS.get(encoding, "utf-8")
    return raw.decode(enc, errors="ignore")


def convert_text_to_hex(text: str, encoding: str = "utf-8") -> str:
    """文本转十六进制字符串（大写，空格分隔）"""
    return _encode_text(text, encoding).hex(" ").upper()
