"""
MAC 厂商（OUI）查询工具（网络扫描模块）。

**零第三方依赖**：不使用 ``mac-vendor-lookup``（该包会拉入 aiohttp 等整套依赖，
且运行时才从 IEEE 官网下载厂商库并缓存到 ``sys.prefix``，打包后现场无外网即失效）。

改为读取随程序打包的数据文件 ``data/oui.txt``：
- 每行格式 ``OUI:厂商名``，OUI 为大写 6 位十六进制（MAC 前 3 字节）
- 启动时懒加载为 ``dict{oui_hex: vendor}``，查询时取 MAC 前 6 位十六进制查表
- 未命中返回空字符串

数据文件路径兼容两种打包形态：
- onefile：``sys._MEIPASS/data/oui.txt``
- onedir ：``<exe目录>/_internal/data/oui.txt``
- 开发环境：``<backend>/data/oui.txt``
"""

import sys
import threading
from pathlib import Path
from typing import Dict, Optional

_OUI_FILENAME = "oui.txt"
_MAC_HEX_CHARS = frozenset("0123456789ABCDEFabcdef")

_table_lock = threading.Lock()
_vendor_table: Optional[Dict[str, str]] = None


def _candidate_paths() -> list:
    """按优先级返回 oui.txt 的候选路径列表"""
    candidates = []

    # onefile：PyInstaller 解压临时目录
    meipass = getattr(sys, "_MEIPASS", None)
    if meipass:
        candidates.append(Path(meipass) / "data" / _OUI_FILENAME)

    # 打包（onedir / onefile 兜底）：exe 同级的 _internal 或直接 data
    if getattr(sys, "frozen", False):
        exe_dir = Path(sys.executable).resolve().parent
        candidates.append(exe_dir / "_internal" / "data" / _OUI_FILENAME)
        candidates.append(exe_dir / "data" / _OUI_FILENAME)

    # 开发环境：backend/data/oui.txt
    candidates.append(Path(__file__).resolve().parent.parent / "data" / _OUI_FILENAME)

    return candidates


def resolve_oui_path() -> Optional[Path]:
    """返回实际存在的 oui.txt 路径；都不存在返回 None"""
    for path in _candidate_paths():
        try:
            if path.exists():
                return path
        except Exception:
            continue
    return None


def _load_table() -> Dict[str, str]:
    """加载并缓存 OUI 表（线程安全，懒加载）"""
    global _vendor_table
    if _vendor_table is not None:
        return _vendor_table

    with _table_lock:
        if _vendor_table is not None:
            return _vendor_table

        table: Dict[str, str] = {}
        path = resolve_oui_path()
        if path is not None:
            try:
                with open(path, "r", encoding="utf-8", errors="ignore") as file:
                    for line in file:
                        line = line.strip()
                        if not line or ":" not in line:
                            continue
                        oui, _, vendor = line.partition(":")
                        oui = oui.strip().upper()
                        vendor = vendor.strip()
                        if len(oui) == 6 and vendor:
                            table[oui] = vendor
            except Exception:
                # 读取失败时保持空表，查询统一返回空字符串（不影响扫描主流程）
                table = {}

        _vendor_table = table
        return _vendor_table


def normalize_mac(mac: str) -> str:
    """去除分隔符并转大写，返回纯十六进制字符串（非法字符一律丢弃）"""
    return "".join(ch for ch in (mac or "") if ch in _MAC_HEX_CHARS).upper()


def lookup_vendor(mac: str) -> str:
    """
    由 MAC 查询厂商名。

    Args:
        mac: MAC 地址（``AA:BB:CC:DD:EE:FF`` / ``AABBCCDDEEFF`` / ``AA-BB-CC-..``）

    Returns:
        厂商名；未命中或无法解析返回空字符串
    """
    key = normalize_mac(mac)
    if len(key) < 6:
        return ""
    return _load_table().get(key[:6], "")


def is_table_loaded() -> bool:
    """OUI 表是否已加载（供自测使用）"""
    return _vendor_table is not None


def table_size() -> int:
    """已加载的 OUI 条目数（触发懒加载）"""
    return len(_load_table())


if __name__ == "__main__":
    print(f"oui.txt 路径: {resolve_oui_path()}")
    print(f"条目数: {table_size()}")
    for sample in ["A4:2B:B0:11:22:33", "3C5AB4CCDD02", "E0-50-8B-11-22-04", "FF:FF:FF:00:00:00"]:
        print(f"  {sample:<20} -> {lookup_vendor(sample)!r}")
