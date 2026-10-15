"""
HTTP Server 服务 - ``HttpServerManager``（HTTP Server 模块内核，第五模式）。

职责：
- 在本机启动一个 HTTP 服务端（默认端口 8080，可自定义），供外部 client 发数据过来
- 任意方法（GET/POST/PUT/DELETE/PATCH/HEAD/OPTIONS）、任意路径均接收并记录
- 记录入内存环形队列（``collections.deque``），WebSocket 50ms 轮询推送（对齐项目既定范式）
- 按响应配置返回：状态码 / Content-Type / 自定义 body / 延迟 / **echo 回显（默认开启）**

技术选型（关键决策，勿改）：
使用标准库 ``http.server.ThreadingHTTPServer`` 而非 FastAPI/uvicorn。
原因：本模块需要「任意路径 + 任意方法 + 用户自定义端口」，且同一端口上的所有请求
都必须被本模块接住；而主程序的 FastAPI 是固定 API 路由（内部端口 20001+），
两者定位冲突。ThreadingHTTPServer 每请求独立线程，天然满足且**零新增依赖**。

参考竞品：webhook.site / hookcatch / tarampampam/webhook-tester（被动接收型）；
这类工具的核心即「记录请求 + 可配置响应」，本实现对齐该形态。

**零第三方依赖**：仅使用标准库 + 项目内 ``utils`` 工具。
"""

import collections
import csv
import ctypes
import json
import logging
import os
import socket
import struct
import threading
import time
import uuid
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlsplit

from config import settings
from models import APIResponse, HttpServerConfig
from utils.netif_utils import (
    _ip_sort_key,
    _windows_iface_types,
    classify_ip,
    RANK_LOOPBACK,
)

logger = logging.getLogger(__name__)

# 记录条数上限从配置取（内存环形队列）
MAX_RECORDS: int = settings.HTTP_MAX_RECORDS
# 单请求体读取上限
MAX_BODY: int = settings.HTTP_MAX_BODY
# 二进制判定：解码探测长度
BINARY_SNIFF_LEN: int = 4096

# 本程序自用端口段（禁止作为监听端口，避免与前端/后端自身端口冲突）
RESERVED_PORT_START: int = settings.HTTP_RESERVED_PORT_START
RESERVED_PORT_END: int = settings.HTTP_RESERVED_PORT_END

# 前端轮询节奏
POLL_INTERVAL: float = 0.05
HEARTBEAT_INTERVAL: float = 1.0

# 支持的 HTTP 方法（通吃，未知方法也记录）
SUPPORTED_METHODS = ("GET", "POST", "PUT", "DELETE", "PATCH", "HEAD", "OPTIONS")


def _is_binary(data: bytes) -> bool:
    """判定字节流是否为二进制（含 NUL 或 UTF-8 解码失败即视为二进制）"""
    if not data:
        return False
    sample = data[:BINARY_SNIFF_LEN]
    if b"\x00" in sample:
        return True
    try:
        sample.decode("utf-8")
        return False
    except UnicodeDecodeError:
        return True


def _to_text(data: bytes) -> str:
    """字节流尽力解码为文本（失败则 latin-1 兜底，保证不抛异常）"""
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        pass
    try:
        return data.decode("gbk")
    except UnicodeDecodeError:
        return data.decode("latin-1", errors="replace")


def _to_hex(data: bytes) -> str:
    """字节流转大写十六进制（空格分隔，便于现场比对）"""
    if not data:
        return ""
    return " ".join(f"{byte:02X}" for byte in data)


def _port_in_use(port: int, bind: str = "0.0.0.0") -> bool:
    """探测端口是否已被占用（用于启动前给出明确报错）"""
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        probe.settimeout(0.4)
        # Windows 不设 SO_REUSEADDR，保证探测结果真实
        probe.bind((bind, port))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def _list_access_addresses() -> List[Dict[str, str]]:
    """
    列出本机所有可用于访问该 HTTP 服务的地址（供前端展示 / 复制）。

    回环固定为 127.0.0.1（localhost），其余按网卡类别排序（有线→无线→虚拟→其他），
    便于现场把「局域网地址」直接发给对方 client。
    """
    entries: List[Tuple[str, int, str]] = []
    try:
        iftypes = _windows_iface_types()
    except Exception:
        iftypes = {}

    try:
        import psutil

        interfaces = psutil.net_if_addrs()
    except Exception:
        interfaces = {}

    seen = set()
    for iface, addrs in (interfaces or {}).items():
        iftype, desc = iftypes.get((iface or "").lower(), (None, ""))
        for addr in addrs:
            if getattr(addr, "family", None) != socket.AF_INET:
                continue
            ip = addr.address
            if ip.startswith("169.254."):
                continue
            if ip in seen:
                continue
            seen.add(ip)
            if ip.startswith("127."):
                continue
            rank = classify_ip(iface, ip, iftype, desc)
            entries.append((ip, rank, iface or ""))

    entries.sort(key=lambda item: (item[1], _ip_sort_key(item[0])))

    result: List[Dict[str, str]] = [
        {"ip": "127.0.0.1", "label": "本机", "interface": "loopback", "rank": str(RANK_LOOPBACK)}
    ]
    for ip, rank, iface in entries:
        result.append(
            {"ip": ip, "label": "局域网" if rank != RANK_LOOPBACK else "本机", "interface": iface, "rank": str(rank)}
        )
    return result


class _Handler(BaseHTTPRequestHandler):
    """
    全方法通吃的请求处理器。

    任何方法、任何路径的请求都会走到 ``_handle_common``：
    记录请求 → 按配置生成响应（默认 echo 回显）。
    """

    # HTTP/1.1 必须正确发 Content-Length，否则客户端会挂起等待
    protocol_version = "HTTP/1.1"
    # 静默默认日志（自带 log 会写 stderr，打包后可能不可用）
    server_version = "DebugAssistant-HTTP"
    sys_version = ""

    # ------------------------------------------------------------------
    # 将 7 个标准方法全部指向同一处理函数
    # ------------------------------------------------------------------
    def do_GET(self):  # noqa: N802
        self._handle_common("GET")

    def do_POST(self):  # noqa: N802
        self._handle_common("POST")

    def do_PUT(self):  # noqa: N802
        self._handle_common("PUT")

    def do_DELETE(self):  # noqa: N802
        self._handle_common("DELETE")

    def do_PATCH(self):  # noqa: N802
        self._handle_common("PATCH")

    def do_HEAD(self):  # noqa: N802
        self._handle_common("HEAD")

    def do_OPTIONS(self):  # noqa: N802
        self._handle_common("OPTIONS")

    # 未知方法（如 TRACE / PROPFIND）也接住并记录
    def handle_one_request(self):  # noqa: D102
        try:
            BaseHTTPRequestHandler.handle_one_request(self)
        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True

    # ------------------------------------------------------------------
    # 请求体读取
    # ------------------------------------------------------------------
    def _read_body(self) -> bytes:
        """
        读取请求体。支持 Content-Length 与 chunked 两种编码。

        超长体按 MAX_BODY 截断（仅读取上限内的字节，剩余丢弃），避免内存被打爆。
        """
        transfer_encoding = (self.headers.get("Transfer-Encoding") or "").lower()
        if "chunked" in transfer_encoding:
            return self._read_chunked_body()

        length_text = self.headers.get("Content-Length")
        if not length_text:
            return b""
        try:
            length = int(length_text)
        except (TypeError, ValueError):
            return b""
        if length <= 0:
            return b""

        read_len = min(length, MAX_BODY)
        body = self.rfile.read(read_len)
        # 超出上限的部分必须读掉，否则 keep-alive 连接会串包
        remaining = length - read_len
        while remaining > 0:
            chunk = self.rfile.read(min(remaining, 65536))
            if not chunk:
                break
            remaining -= len(chunk)
        return body

    def _read_chunked_body(self) -> bytes:
        """读取 chunked 编码请求体（上限 MAX_BODY）"""
        chunks: List[bytes] = []
        total = 0
        while True:
            line = self.rfile.readline(65536)
            if not line:
                break
            size_text = line.split(b";", 1)[0].strip()
            try:
                size = int(size_text, 16)
            except ValueError:
                break
            if size == 0:
                # 吃掉 trailer
                while True:
                    trailer = self.rfile.readline(65536)
                    if not trailer or trailer in (b"\r\n", b"\n"):
                        break
                break
            if total + size > MAX_BODY:
                size = max(0, MAX_BODY - total)
            if size == 0:
                # 继续读掉剩余数据
                self.rfile.read(65536)
                break
            data = self.rfile.read(size)
            chunks.append(data)
            total += len(data)
            self.rfile.read(2)  # CRLF
        return b"".join(chunks)

    # ------------------------------------------------------------------
    # 统一处理
    # ------------------------------------------------------------------
    def _handle_common(self, method: str) -> None:
        try:
            raw_path = self.path or "/"
            split = urlsplit(raw_path)

            body = self._read_body() if method != "HEAD" else b""

            # 请求头（保持原始顺序，同名头合并为列表）
            headers: Dict[str, Any] = {}
            for key, value in self.headers.items():
                if key in headers:
                    existing = headers[key]
                    if isinstance(existing, list):
                        existing.append(value)
                    else:
                        headers[key] = [existing, value]
                else:
                    headers[key] = value

            client_ip = self.client_address[0] if self.client_address else ""
            client_port = self.client_address[1] if self.client_address else 0

            binary = _is_binary(body)
            record = {
                "id": uuid.uuid4().hex[:12],
                "method": method,
                "path": split.path or "/",
                "raw_path": raw_path,
                "query": split.query,
                "http_version": self.request_version,
                "headers": headers,
                "client_ip": client_ip,
                "client_port": client_port,
                "body_size": len(body),
                "content_type": self.headers.get("Content-Type", "") or "",
                "is_binary": binary,
                "body": "" if binary else _to_text(body),
                "body_hex": _to_hex(body) if binary else "",
                "timestamp": time.time(),
                "truncated": len(body) >= MAX_BODY,
            }

            manager = self.server.manager  # type: ignore[attr-defined]
            manager._add_record(record)

            self._send_response(method, body)

        except (BrokenPipeError, ConnectionResetError, ConnectionAbortedError):
            self.close_connection = True
        except Exception as exc:  # 兜底：绝不让异常穿透到 server 线程外
            logger.exception("HTTP Server 处理请求失败: %s", exc)
            try:
                self._send_simple(500, "text/plain; charset=utf-8", b"500 Internal Error")
            except Exception:
                self.close_connection = True

    def _send_response(self, method: str, request_body: bytes) -> None:
        """按响应配置构造并发送响应"""
        manager = self.server.manager  # type: ignore[attr-defined]
        config = manager.get_response_config()

        delay_ms = int(config.get("delay_ms") or 0)
        if delay_ms > 0:
            # 上限 60s，避免误填导致连接长时间悬挂
            time.sleep(min(delay_ms, 60000) / 1000.0)

        code = int(config.get("code") or 200)
        if code < 100 or code > 599:
            code = 200

        echo = bool(config.get("echo", True))
        if echo:
            payload = request_body
            content_type = (
                self.headers.get("Content-Type") or "application/octet-stream"
            )
        else:
            body_text = config.get("body") or ""
            payload = body_text.encode("utf-8")
            content_type = config.get("content_type") or "text/plain; charset=utf-8"

        if method == "HEAD":
            # HEAD 只回首部，不返回正文
            self._send_simple(code, content_type, b"", send_body=False)
        else:
            self._send_simple(code, content_type, payload)

    def _send_simple(
        self, code: int, content_type: str, payload: bytes, send_body: bool = True
    ) -> None:
        """发送响应（HTTP/1.1 必须带 Content-Length）"""
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(payload)))
        # 便于现场联调时确认是本工具回复的
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "*")
        self.end_headers()
        if send_body and payload:
            self.wfile.write(payload)

    # 关闭默认 stderr 日志（打包后 sys.stderr 可能为 None）
    def log_message(self, fmt, *args):  # noqa: A003
        return

    def log_error(self, fmt, *args):  # noqa: A003
        return


class HttpServerManager:
    """HTTP Server 管理器 —— 单实例模型，请求记录队列推送"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._server: Optional[ThreadingHTTPServer] = None
        self._thread: Optional[threading.Thread] = None
        self._session_id: Optional[str] = None
        self._config: Dict[str, Any] = {
            "port": settings.HTTP_DEFAULT_PORT,
            "bind": settings.HTTP_DEFAULT_BIND,
            "response": {
                "code": 200,
                "content_type": "application/json",
                "body": "",
                "delay_ms": 0,
                "echo": True,
            },
        }
        self._records: collections.deque = collections.deque(maxlen=MAX_RECORDS)
        self._queue: collections.deque = collections.deque()
        self._total: int = 0
        self._started_at: Optional[float] = None
        self._last_error: Optional[str] = None

    # ------------------------------------------------------------------
    # 生命周期
    # ------------------------------------------------------------------
    def start(self, config: HttpServerConfig) -> APIResponse:
        """启动 HTTP 服务端"""
        with self._lock:
            if self._server is not None:
                return APIResponse(success=False, message="HTTP 服务已在运行，请先停止")

        port = int(config.port or settings.HTTP_DEFAULT_PORT)
        bind = (config.bind or settings.HTTP_DEFAULT_BIND).strip()

        if port < 1 or port > 65535:
            return APIResponse(success=False, message=f"端口不合法: {port}（应在 1~65535）")

        if RESERVED_PORT_START <= port <= RESERVED_PORT_END:
            return APIResponse(
                success=False,
                message=f"端口 {port} 属本程序自用段（{RESERVED_PORT_START}~{RESERVED_PORT_END}），请换一个",
            )

        if bind not in ("0.0.0.0", "") and bind != "127.0.0.1":
            try:
                socket.inet_aton(bind)
            except OSError:
                return APIResponse(success=False, message=f"绑定地址不合法: {bind}")

        if _port_in_use(port, bind or "0.0.0.0"):
            return APIResponse(
                success=False,
                message=f"端口 {port} 已被占用，请换一个端口或先关闭占用程序",
            )

        server: Optional[ThreadingHTTPServer] = None
        try:
            server = ThreadingHTTPServer((bind or "0.0.0.0", port), _Handler)
            server.daemon_threads = True
            server.manager = self  # type: ignore[attr-defined]
            server.allow_reuse_address = False
        except OSError as exc:
            return APIResponse(success=False, message=f"启动失败: {exc}")

        session_id = uuid.uuid4().hex
        with self._lock:
            self._server = server
            self._session_id = session_id
            self._config = {
                "port": port,
                "bind": bind or "0.0.0.0",
                "response": config.response.model_dump(),
            }
            self._records.clear()
            self._queue.clear()
            self._total = 0
            self._started_at = time.time()
            self._last_error = None

        thread = threading.Thread(
            target=self._serve, args=(server,), name="http-server", daemon=True
        )
        self._thread = thread
        thread.start()

        logger.info("HTTP 服务已启动: %s:%d (session=%s)", bind or "0.0.0.0", port, session_id)
        return APIResponse(
            success=True,
            message=f"HTTP 服务已启动，监听 {bind or '0.0.0.0'}:{port}",
            data={
                "session_id": session_id,
                "port": port,
                "bind": bind or "0.0.0.0",
                "addresses": _list_access_addresses(),
            },
        )

    def _serve(self, server: ThreadingHTTPServer) -> None:
        """服务线程入口（异常收敛，避免静默退出）"""
        try:
            server.serve_forever(poll_interval=0.2)
        except Exception as exc:
            logger.exception("HTTP 服务线程异常: %s", exc)
            with self._lock:
                self._last_error = str(exc)

    def stop(self) -> APIResponse:
        """停止 HTTP 服务端（保留已记录数据，便于停止后回看）"""
        with self._lock:
            server = self._server
            session_id = self._session_id
            self._server = None
            self._session_id = None

        if server is None:
            return APIResponse(success=False, message="HTTP 服务未在运行")

        try:
            server.shutdown()
        except Exception:
            pass
        try:
            server.server_close()
        except Exception:
            pass

        thread = self._thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            self._thread = None

        logger.info("HTTP 服务已停止: %s", session_id)
        return APIResponse(success=True, message="HTTP 服务已停止", data={"session_id": session_id})

    def status(self) -> Dict[str, Any]:
        """返回当前状态快照"""
        with self._lock:
            running = self._server is not None
            session_id = self._session_id
            config = json.loads(json.dumps(self._config))
            total = self._total
            started_at = self._started_at
            last_error = self._last_error
            count = len(self._records)

        port = config.get("port")
        bind = config.get("bind")
        addresses = _list_access_addresses() if running else []
        for item in addresses:
            item["url"] = f"http://{item['ip']}:{port}/"

        return {
            "running": running,
            "session_id": session_id,
            "port": port,
            "bind": bind,
            "response": config.get("response"),
            "total": total,
            "count": count,
            "started_at": started_at,
            "elapsed": (time.time() - started_at) if (running and started_at) else 0,
            "addresses": addresses,
            "last_error": last_error,
        }

    def is_running(self) -> bool:
        return self._server is not None

    def get_session_id(self) -> Optional[str]:
        return self._session_id

    # ------------------------------------------------------------------
    # 响应配置
    # ------------------------------------------------------------------
    def set_response_config(self, response: Dict[str, Any]) -> APIResponse:
        """更新响应配置（运行中也可实时生效）"""
        with self._lock:
            current = dict(self._config.get("response") or {})
            for key in ("code", "content_type", "body", "delay_ms", "echo"):
                if key in response and response[key] is not None:
                    current[key] = response[key]
            try:
                current["code"] = max(100, min(599, int(current.get("code") or 200)))
            except (TypeError, ValueError):
                current["code"] = 200
            try:
                current["delay_ms"] = max(0, min(60000, int(current.get("delay_ms") or 0)))
            except (TypeError, ValueError):
                current["delay_ms"] = 0
            current["echo"] = bool(current.get("echo", True))
            self._config["response"] = current
        return APIResponse(success=True, message="响应配置已更新", data={"response": current})

    def get_response_config(self) -> Dict[str, Any]:
        """返回响应配置副本（供请求处理器读取）"""
        with self._lock:
            return dict(self._config.get("response") or {})

    # ------------------------------------------------------------------
    # 记录
    # ------------------------------------------------------------------
    def _add_record(self, record: Dict[str, Any]) -> None:
        """新增一条请求记录并推入事件队列（供 WS 消费）"""
        with self._lock:
            self._records.append(record)
            self._total += 1
            self._queue.append(record)

    def read_event(self) -> Optional[Dict[str, Any]]:
        """从队列取一条记录；无数据返回 None（供 WS 50ms 轮询）"""
        with self._lock:
            if not self._queue:
                return None
            try:
                return self._queue.popleft()
            except Exception:
                return None

    def get_records(self) -> List[Dict[str, Any]]:
        """返回全部记录（供前端刷新后恢复）"""
        with self._lock:
            return [dict(item) for item in self._records]

    def get_record(self, record_id: str) -> Optional[Dict[str, Any]]:
        """按 id 查询单条记录"""
        with self._lock:
            for item in self._records:
                if item.get("id") == record_id:
                    return dict(item)
        return None

    def clear(self) -> APIResponse:
        """清空请求记录（不影响运行状态）"""
        with self._lock:
            count = len(self._records)
            self._records.clear()
            self._queue.clear()
        return APIResponse(success=True, message=f"已清空 {count} 条请求记录", data={"count": count})


# 实例化 HTTP Server 管理器
http_server_manager = HttpServerManager()


# ----------------------------------------------------------------------
# 导出（供路由复用）
# ----------------------------------------------------------------------
def export_records(
    records: List[Dict[str, Any]], directory: str = "", filename: str = ""
) -> Dict[str, Any]:
    """
    将请求记录导出为日志文本（UTF-8 带 BOM）。

    Args:
        records: 记录列表
        directory: 目标目录；为空则使用当前工作目录
        filename: 文件名；为空则自动生成 ``http_log_<时间>.txt``

    Returns:
        ``{"path", "count", "size"}``
    """
    target_dir = (directory or "").strip() or os.getcwd()
    os.makedirs(target_dir, exist_ok=True)

    name = (filename or "").strip()
    if not name:
        name = f"http_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.txt"
    elif not name.lower().endswith(".txt"):
        name += ".txt"

    path = os.path.join(target_dir, name)
    _ORDERED_KEYS = (
        "timestamp",
        "method",
        "raw_path",
        "client_ip",
        "client_port",
        "http_version",
        "content_type",
        "body_size",
        "is_binary",
        "body",
        "body_hex",
        "headers",
    )

    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        file.write(f"# 调试助手 HTTP Server 请求日志  导出时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
        file.write(f"# 共 {len(records)} 条\n\n")
        for index, record in enumerate(records, start=1):
            ts = record.get("timestamp")
            ts_text = (
                datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
                if isinstance(ts, (int, float))
                else ""
            )
            file.write(f"{'=' * 72}\n")
            file.write(f"[{index}] {ts_text}\n")
            file.write(f"{record.get('method', '')} {record.get('raw_path', '')} {record.get('http_version', '')}\n")
            file.write(f"来源: {record.get('client_ip', '')}:{record.get('client_port', '')}\n")
            file.write(f"大小: {record.get('body_size', 0)} 字节\n")
            headers = record.get("headers") or {}
            if headers:
                for key, value in headers.items():
                    if isinstance(value, list):
                        for one in value:
                            file.write(f"  {key}: {one}\n")
                    else:
                        file.write(f"  {key}: {value}\n")
            if record.get("body"):
                file.write("--- Body (文本) ---\n")
                file.write(str(record.get("body")) + "\n")
            if record.get("body_hex"):
                file.write("--- Body (HEX) ---\n")
                file.write(str(record.get("body_hex")) + "\n")
            file.write("\n")

    return {"path": path, "count": len(records), "size": os.path.getsize(path)}
