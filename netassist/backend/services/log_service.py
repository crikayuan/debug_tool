"""
日志写盘服务
支持编码 utf-8 / utf-8-bom / gbk，追加模式
"""

import os


ENCODING_MAP = {
    "utf-8": "utf-8",
    "utf8": "utf-8",
    "utf-8-bom": "utf-8-sig",
    "gbk": "gbk",
    "ansi": "gbk",
}


def save_log(filename: str, directory: str, content: str, encoding: str = "utf-8") -> dict:
    """
    将日志内容写入文件（追加模式）。

    Returns:
        {"path", "size"}
    """
    enc = ENCODING_MAP.get(encoding, "utf-8")
    os.makedirs(directory, exist_ok=True)
    path = os.path.join(directory, filename)

    with open(path, "a", encoding=enc) as f:
        f.write(content)

    return {"path": path, "size": os.path.getsize(path)}
