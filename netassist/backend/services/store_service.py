"""
本地数据持久化服务：把快捷指令、批量发送、历史、自动应答、设置等存到本机文件。

存储位置优先级：
1. %LOCALAPPDATA%\\调试助手\\store.json（用户目录，重装程序不丢）
2. 程序目录 data\\store.json（兜底）
"""
import json
import os
import threading
from pathlib import Path

_lock = threading.Lock()
_file_cache = None


def _data_dir() -> Path:
    """确定数据目录"""
    candidates = []
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "调试助手")
    candidates.append(Path.home() / "调试助手")
    candidates.append(Path(__file__).resolve().parent.parent / "data")

    for d in candidates:
        try:
            d.mkdir(parents=True, exist_ok=True)
            # 写权限探测
            probe = d / ".write_test"
            probe.write_text("1", encoding="utf-8")
            probe.unlink()
            return d
        except Exception:
            continue
    return Path(__file__).resolve().parent.parent


def _file() -> Path:
    global _file_cache
    if _file_cache is None:
        _file_cache = _data_dir() / "store.json"
    return _file_cache


def get_store_path() -> str:
    return str(_file())


def load_all() -> dict:
    p = _file()
    if not p.exists():
        return {}
    try:
        with open(p, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data if isinstance(data, dict) else {}
    except Exception:
        return {}


def get(key: str):
    return load_all().get(key)


def set_value(key: str, value) -> bool:
    with _lock:
        data = load_all()
        data[key] = value
        p = _file()
        tmp = p.with_name(p.name + ".tmp")
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, p)
        return True
