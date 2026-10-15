"""
网络扫描服务 - ``ScanManager``（网络扫描模块内核）。

职责：
- 任务生命周期（start / stop / get_result / get_progress），同一时刻仅一个任务在跑
- ``ThreadPoolExecutor`` 并发 TCP 存活探测（默认 128，允许 8~512）
- 探测流程（对齐设计文档 §4.1）：
  1) 先并发 TCP 探测整个网段（同时唤醒 ARP 缓存，判定存活与开放端口）
  2) 扫描结束后一次性读取 ARP 表，把 MAC 补到对应 IP 上
  3) 对在线 IP 并发做反向 DNS 解析主机名
  4) 用 MAC 的 OUI 前缀查厂商
- 结果放入队列供 WebSocket 50ms 轮询取用；进度统计（已扫描数 / 总数 / 在线数 / 耗时）
- 线程安全（``threading.Lock``），停止标志可中断

探测判活说明：TCP ``connect_ex`` 返回 0（端口开放）或连接被拒绝/重置（对端回了 RST）
都说明主机存活；仅当所有端口均超时/不可达才判定为离线。相比只看开放端口，
此策略可显著提高「设备发现率」（很多设备关掉了常见端口但仍在线）。

**零第三方依赖**：仅使用标准库 + 项目内 ``utils`` 工具。
"""

import collections
import csv
import logging
import os
import socket
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Any, Dict, List, Optional

from models import APIResponse, ScanConfig
from utils.arp_utils import get_arp_table
from utils.ip_range_utils import parse_scan_range
from utils.vendor_utils import lookup_vendor

logger = logging.getLogger(__name__)

# 默认存活探测端口（关闭端口探测开关时仍用于判活，取 UI「常用」方案）
DEFAULT_PROBE_PORTS: List[int] = [80, 443, 22, 445, 3389]

DEFAULT_CONCURRENCY: int = 128
MIN_CONCURRENCY: int = 8
MAX_CONCURRENCY: int = 512

DEFAULT_TIMEOUT_MS: int = 500
MIN_TIMEOUT_MS: int = 50
MAX_TIMEOUT_MS: int = 10000

DNS_TIMEOUT_S: float = 1.0
MAX_KEPT_TASKS: int = 20

# connect_ex 返回值：连接被拒绝 / 被重置 仍说明主机存活
# 10061 WSAECONNREFUSED, 10054 WSAECONNRESET (Windows)；111 / 104 (POSIX)
_REFUSED_CODES = frozenset({10061, 10054, 111, 104})

_TERMINAL_STATUS = ("done", "stopped", "error")


def _ips_to_cidr(ips: List[str]) -> str:
    """
    从 IP 列表推算最简 CIDR：取最小与最大 IP，二者必须位于同一网络。

    Returns:
        CIDR 字符串（如 ``192.168.1.0/24``），无法计算时返回空串
    """
    if not ips:
        return ""
    try:
        import ipaddress as _ip

        addrs = sorted({_ip.IPv4Address(ip) for ip in ips})
    except Exception:
        return ""
    if not addrs:
        return ""
    lo = addrs[0]
    hi = addrs[-1]
    if lo == hi:
        return f"{lo}/32"
    # 找出 lo 与 hi 共同的最长前缀（即最小的网络）
    lo_int = int(lo)
    hi_int = int(hi)
    if lo_int == hi_int:
        return f"{lo}/32"
    # 从 /32 往下试，找到第一个 lo==net 且 hi==broadcast 的前缀
    for prefix in range(32, 0, -1):
        mask = (0xFFFFFFFF << (32 - prefix)) & 0xFFFFFFFF
        if (lo_int & mask) == (hi_int & mask):
            net = _ip.IPv4Address(lo_int & mask)
            return f"{net}/{prefix}"
    return f"{lo}/32"


def _compute_changes(
    previous: List[Dict[str, Any]], current: List[Dict[str, Any]]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    对比上一轮与本轮扫描结果，得：
    - new: 本轮有但上一轮没有
    - left: 上一轮有但本轮没有
    - changed: IP 还在但 MAC 改了（疑似 IP 冲突/换设备）
    """
    prev_by_ip: Dict[str, Dict[str, Any]] = {it.get("ip"): it for it in previous if it.get("ip")}
    curr_by_ip: Dict[str, Dict[str, Any]] = {it.get("ip"): it for it in current if it.get("ip")}

    new = []
    left = []
    changed = []

    for ip, it in curr_by_ip.items():
        if ip not in prev_by_ip:
            new.append({"ip": ip, "mac": it.get("mac", ""), "vendor": it.get("vendor", "")})
        else:
            prev_mac = (prev_by_ip[ip].get("mac") or "").upper()
            curr_mac = (it.get("mac") or "").upper()
            if prev_mac and curr_mac and prev_mac != curr_mac:
                changed.append(
                    {
                        "ip": ip,
                        "from_mac": prev_mac,
                        "to_mac": curr_mac,
                        "vendor": it.get("vendor", ""),
                    }
                )

    for ip, it in prev_by_ip.items():
        if ip not in curr_by_ip:
            left.append({"ip": ip, "mac": it.get("mac", ""), "vendor": it.get("vendor", "")})

    return {"new": new, "left": left, "changed": changed}


class ScanManager:
    """网络扫描管理器 —— 单任务模型，线程池并发探测 + 结果队列推送"""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._current_task_id: Optional[str] = None

    # ------------------------------------------------------------------
    # 任务生命周期
    # ------------------------------------------------------------------
    def start(self, config: ScanConfig) -> APIResponse:
        """
        启动一次扫描（若已有任务在跑，先停止旧的）。

        Returns:
            APIResponse，成功时 ``data={"task_id", "total", "cidr"}``
        """
        concurrency = self._clamp_int(
            config.concurrency, DEFAULT_CONCURRENCY, MIN_CONCURRENCY, MAX_CONCURRENCY
        )
        timeout_ms = self._clamp_int(
            config.timeout_ms, DEFAULT_TIMEOUT_MS, MIN_TIMEOUT_MS, MAX_TIMEOUT_MS
        )

        # 解析扫描范围（非法范围返回明确错误，由路由转 400，而非 500）
        expr = (config.range or "").strip()
        try:
            if expr:
                ips = parse_scan_range(expr)
            else:
                ips = parse_scan_range(
                    (config.start_ip or "").strip(), (config.end_ip or "").strip()
                )
        except ValueError as exc:
            return APIResponse(success=False, message=f"扫描范围错误: {exc}")

        if not ips:
            return APIResponse(success=False, message="扫描范围为空，请填写有效的 IP 范围")

        # 推算 CIDR（取最小与最大 IP 拼成 /N）；失败则用第一个 IP 作为占位
        cidr = _ips_to_cidr(ips)

        # 同刻仅一个任务：先停掉当前任务
        with self._lock:
            current = self._current_task_id
        if current:
            self.stop(current)

        # 找最近一次扫描的结果（用于「本次新增/离开/改 IP-MAC」对比）
        # 规则：取所有非当前 task_id 中按 started_at 倒序最新一个；保留空结果
        # （即"上一轮扫了什么、什么也没扫到"也算作"上一轮"，这样新出现的设备会被标 new）
        previous_items: List[Dict[str, Any]] = []
        latest_started = -1.0
        with self._lock:
            for tid, t in self._tasks.items():
                if tid == self._current_task_id:
                    continue
                started = t.get("started_at") or 0
                if started > latest_started:
                    latest_started = started
                    previous_items = [dict(it) for it in t.get("results", {}).values()]

        task_id = uuid.uuid4().hex
        task: Dict[str, Any] = {
            "task_id": task_id,
            "config": config.model_dump(),
            "ips": ips,
            "cidr": cidr,
            "total": len(ips),
            "scanned": 0,
            "online": 0,
            "offline": 0,
            "results": {},  # ip -> item dict（仅存活/已发现设备）
            "queue": collections.deque(),
            "stop_event": threading.Event(),
            "status": "running",
            "started_at": time.time(),
            "finished_at": None,
            "error": None,
            "concurrency": concurrency,
            "timeout_s": timeout_ms / 1000.0,
            "thread": None,
            "previous_items": previous_items,  # 用于计算变化（new/left/changed）
            "changes": {"new": [], "left": [], "changed": []},  # 运行结束时填
        }

        with self._lock:
            self._tasks[task_id] = task
            self._current_task_id = task_id
            self._prune_tasks_locked()

        thread = threading.Thread(
            target=self._run_scan,
            args=(task_id,),
            name=f"scan-{task_id[:8]}",
            daemon=True,
        )
        task["thread"] = thread
        thread.start()

        logger.info("扫描任务已启动: %s，CIDR=%s，共 %d 个地址，并发 %d", task_id, cidr, len(ips), concurrency)
        return APIResponse(
            success=True,
            message=f"扫描已启动，共 {len(ips)} 个地址",
            data={"task_id": task_id, "total": len(ips), "cidr": cidr},
        )

    def stop(self, task_id: str) -> APIResponse:
        """停止指定任务（已完成结果保留）"""
        task = self._tasks.get(task_id)
        if task is None:
            return APIResponse(success=False, message="扫描任务不存在")

        task["stop_event"].set()
        with self._lock:
            if task["status"] == "running":
                task["status"] = "stopped"
            if self._current_task_id == task_id:
                self._current_task_id = None
        logger.info("扫描任务收到停止请求: %s", task_id)
        return APIResponse(success=True, message="扫描已停止", data={"task_id": task_id})

    # ------------------------------------------------------------------
    # 查询 / 事件读取
    # ------------------------------------------------------------------
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """返回任务内部 dict（供 WS 端点判断存在性）"""
        return self._tasks.get(task_id)

    def read_event(self, task_id: str) -> Optional[Dict[str, Any]]:
        """从队列取一条事件；无数据返回 None（供 WS 50ms 轮询）"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        queue = task.get("queue")
        if not queue:
            return None
        try:
            return queue.popleft()
        except Exception:
            return None

    def get_progress(self, task_id: str) -> Optional[Dict[str, Any]]:
        """返回进度快照；任务不存在返回 None"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        with self._lock:
            return self._progress_payload(task)

    def get_result(self, task_id: str) -> Optional[Dict[str, Any]]:
        """返回全量结果（供前端刷新恢复）；任务不存在返回 None"""
        task = self._tasks.get(task_id)
        if task is None:
            return None
        with self._lock:
            items = self._sort_items(list(task["results"].values()))
            total = task["total"]
            online = task["online"]
            offline = task["offline"]
            cidr = task.get("cidr") or ""
            changes = dict(task.get("changes") or {})
            return {
                "task_id": task_id,
                "status": task["status"],
                "total": total,
                "scanned": task["scanned"],
                "online": online,
                "offline": offline,
                "occupied": online + offline,
                "utilization": round((online + offline) * 100 / total, 2) if total else 0,
                "cidr": cidr,
                "elapsed": self._elapsed(task),
                "error": task.get("error"),
                "items": [dict(item) for item in items],
                "changes": changes,
            }

    def is_running(self, task_id: str) -> bool:
        """任务是否仍在运行"""
        task = self._tasks.get(task_id)
        return bool(task and task["status"] == "running")

    # ------------------------------------------------------------------
    # 扫描执行
    # ------------------------------------------------------------------
    def _run_scan(self, task_id: str) -> None:
        """后台扫描线程入口（异常统一收敛为 error 状态 + done 事件）"""
        task = self._tasks.get(task_id)
        if task is None:
            return

        config = task["config"]
        ips: List[str] = task["ips"]
        ports = self._resolve_probe_ports(config)
        port_scan = bool(config.get("port_scan"))
        timeout_s = task["timeout_s"]
        concurrency = task["concurrency"]
        stop_event: threading.Event = task["stop_event"]

        try:
            self._phase_tcp_probe(task, ips, ports, port_scan, timeout_s, concurrency, stop_event)
            # 停止后仍做一次 ARP 补全，保留已完成结果
            self._enrich_arp(task)
            # resolve_hostname=False 时跳过 DNS 反查（该开关此前未生效，属既有缺陷）
            if not stop_event.is_set() and config.get("resolve_hostname", True):
                self._enrich_hostnames(task)
            if config.get("vendor_lookup", True):
                self._enrich_vendors(task)
            self._push_final_results(task)
            # 计算本轮 vs 上一轮的变化（即使 stop 也要算，便于复盘）
            with self._lock:
                current_items = list(task["results"].values())
                task["changes"] = _compute_changes(task.get("previous_items") or [], current_items)
        except Exception as exc:  # noqa: BLE001 - 兜底，避免线程静默死亡
            logger.exception("扫描执行异常: %s", exc)
            with self._lock:
                task["error"] = str(exc)
                task["status"] = "error"
                task["finished_at"] = time.time()
            self._enqueue(
                task,
                {
                    "type": "done",
                    "task_id": task_id,
                    "scanned": task["scanned"],
                    "online": task["online"],
                    "offline": task["offline"],
                    "occupied": task["online"] + task["offline"],
                    "utilization": self._utilization(task),
                    "cidr": task.get("cidr") or "",
                    "changes": task.get("changes") or {"new": [], "left": [], "changed": []},
                    "elapsed": self._elapsed(task),
                    "status": "error",
                    "message": str(exc),
                },
            )
            return

        status = "stopped" if stop_event.is_set() else "done"
        with self._lock:
            task["status"] = status
            task["finished_at"] = time.time()
            final_changes = dict(task.get("changes") or {"new": [], "left": [], "changed": []})
            online = task["online"]
            offline = task["offline"]
            cidr = task.get("cidr") or ""
        self._enqueue(
            task,
            {
                "type": "done",
                "task_id": task_id,
                "scanned": task["scanned"],
                "online": online,
                "offline": offline,
                "occupied": online + offline,
                "utilization": self._utilization(task),
                "cidr": cidr,
                "changes": final_changes,
                "elapsed": self._elapsed(task),
                "status": status,
            },
        )
        logger.info(
            "扫描任务结束: %s，状态=%s，已扫描 %d，在线 %d，离线 %d",
            task_id, status, task["scanned"], online, offline,
        )

    def _phase_tcp_probe(
        self,
        task: Dict[str, Any],
        ips: List[str],
        ports: List[int],
        port_scan: bool,
        timeout_s: float,
        concurrency: int,
        stop_event: threading.Event,
    ) -> None:
        """第一阶段：线程池并发 TCP 探测，在线设备逐行推送"""
        executor = ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="scan-probe")
        try:
            futures = {
                executor.submit(
                    self._probe_ip, ip, ports, timeout_s, port_scan, stop_event
                ): ip
                for ip in ips
            }
            for future in as_completed(futures):
                if stop_event.is_set():
                    break
                ip = futures[future]
                try:
                    probe = future.result()
                except Exception:
                    probe = None
                if probe is None:
                    continue
                self._on_probe_done(task, ip, probe, port_scan)
        finally:
            try:
                executor.shutdown(wait=False, cancel_futures=True)
            except TypeError:  # Python < 3.9 兼容
                executor.shutdown(wait=False)

    def _on_probe_done(
        self, task: Dict[str, Any], ip: str, probe: Dict[str, Any], port_scan: bool
    ) -> None:
        """单 IP 探测完成：更新计数、在线结果入表并推送、进度节流推送"""
        item: Optional[Dict[str, Any]] = None
        progress_payload: Optional[Dict[str, Any]] = None
        with self._lock:
            task["scanned"] += 1
            scanned = task["scanned"]
            total = task["total"]

            if probe.get("online"):
                item = {
                    "ip": ip,
                    "mac": "",
                    "vendor": "",
                    "hostname": "",
                    "delay_ms": int(probe.get("delay_ms", 0)),
                    "ports": list(probe.get("ports") or []) if port_scan else [],
                    "online": True,
                }
                task["results"][ip] = item
                task["online"] += 1

            step = max(1, total // 100)
            if scanned % step == 0 or scanned >= total:
                progress_payload = self._progress_payload(task)

        # 在线设备实时逐行推送（MAC/厂商/主机名在 enrich 阶段补全后会再推一次）
        if item is not None:
            self._enqueue(
                task,
                {"type": "result", "task_id": task["task_id"], "item": dict(item)},
            )
        if progress_payload is not None:
            self._enqueue(task, progress_payload)

    def _enrich_arp(self, task: Dict[str, Any]) -> None:
        """
        第二阶段：读 ARP 表（**两次**，间隔 500ms），用于：
        1) 补在线设备的 MAC
        2) 把 ARP 中出现但 TCP 未响应的设备纳入结果（标 offline=True）
        3) 算「离线 = ARP 有但 TCP 不通」
        """
        try:
            arp1 = get_arp_table()
        except Exception:
            arp1 = {}
        # 二次 ARP：填补 TCP 探测时 ARP 缓存尚未填的设备
        time.sleep(0.5)
        try:
            arp2 = get_arp_table()
        except Exception:
            arp2 = {}
        arp = dict(arp1)
        arp.update(arp2)

        ip_set = set(task["ips"])
        with self._lock:
            for ip, item in task["results"].items():
                mac = arp.get(ip)
                if mac:
                    item["mac"] = mac
            for ip, mac in arp.items():
                if ip in ip_set and ip not in task["results"]:
                    # ARP 有记录但 TCP 全部超时：设备存在但不可达
                    task["results"][ip] = {
                        "ip": ip,
                        "mac": mac,
                        "vendor": "",
                        "hostname": "",
                        "delay_ms": 0,
                        "ports": [],
                        "online": False,
                    }
            # 统计：online + offline = total（有结果的设备数）
            online = sum(1 for it in task["results"].values() if it.get("online"))
            offline = sum(1 for it in task["results"].values() if not it.get("online"))
            task["online"] = online
            task["offline"] = offline

    def _enrich_hostnames(self, task: Dict[str, Any]) -> None:
        """第三阶段：对已发现设备并发反向 DNS 解析主机名"""
        with self._lock:
            targets = [
                ip for ip, item in task["results"].items() if not item.get("hostname")
            ]
        if not targets:
            return

        workers = min(32, len(targets))
        try:
            with ThreadPoolExecutor(
                max_workers=workers, thread_name_prefix="scan-dns"
            ) as pool:
                futures = {pool.submit(self._resolve_hostname, ip): ip for ip in targets}
                for future in as_completed(futures):
                    ip = futures[future]
                    try:
                        name = future.result()
                    except Exception:
                        name = ""
                    if name:
                        with self._lock:
                            item = task["results"].get(ip)
                            if item is not None:
                                item["hostname"] = name
        except Exception:
            logger.debug("主机名解析阶段异常", exc_info=True)

    def _enrich_vendors(self, task: Dict[str, Any]) -> None:
        """第四阶段：按 MAC 的 OUI 前缀查厂商名"""
        with self._lock:
            for item in task["results"].values():
                mac = item.get("mac")
                if mac:
                    item["vendor"] = lookup_vendor(mac)

    def _push_final_results(self, task: Dict[str, Any]) -> None:
        """推送补全后的最终结果（按 IP 自然序），供前端按 IP upsert"""
        with self._lock:
            items = self._sort_items(list(task["results"].values()))
        for item in items:
            self._enqueue(
                task,
                {"type": "result", "task_id": task["task_id"], "item": dict(item)},
            )

    # ------------------------------------------------------------------
    # 探测原子操作
    # ------------------------------------------------------------------
    def _probe_ip(
        self,
        ip: str,
        ports: List[int],
        timeout_s: float,
        port_scan: bool,
        stop_event: threading.Event,
    ) -> Optional[Dict[str, Any]]:
        """
        对单个 IP 做 TCP 探测。

        Returns:
            ``{"online", "delay_ms", "ports"}``；被中断返回 None
        """
        if stop_event.is_set():
            return None

        open_ports: List[int] = []
        online = False
        best_delay: Optional[float] = None

        for port in ports:
            if stop_event.is_set():
                break
            status, delay = self._tcp_probe(ip, port, timeout_s)
            if status == "open":
                open_ports.append(port)
                online = True
                if best_delay is None:
                    best_delay = delay
                if not port_scan:
                    break  # 已确认存活，无需继续探测
            elif status == "refused":
                online = True
                if best_delay is None:
                    best_delay = delay
                if not port_scan:
                    break

        return {
            "online": online,
            "delay_ms": (best_delay * 1000.0) if best_delay is not None else 0.0,
            "ports": open_ports,
        }

    @staticmethod
    def _tcp_probe(ip: str, port: int, timeout_s: float):
        """
        单端口 TCP 连接探测。

        Returns:
            (status, delay_seconds)，status ∈ {"open", "refused", "down"}
        """
        sock = None
        rc = -1
        delay = 0.0
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(timeout_s)
            start = time.perf_counter()
            rc = sock.connect_ex((ip, port))
            delay = time.perf_counter() - start
        except Exception:
            return ("down", 0.0)
        finally:
            if sock is not None:
                try:
                    sock.close()
                except Exception:
                    pass

        if rc == 0:
            return ("open", delay)
        if rc in _REFUSED_CODES:
            return ("refused", delay)
        return ("down", delay)

    @staticmethod
    def _resolve_hostname(ip: str, timeout_s: float = DNS_TIMEOUT_S) -> str:
        """
        反向 DNS 解析，带超时保护。

        ``socket.gethostbyaddr`` 在无 PTR 记录时可能长时间阻塞，
        这里用 daemon 线程 + join(timeout) 兜底，超时返回空字符串。
        """
        holder = {"name": ""}

        def worker() -> None:
            try:
                host, _aliases, _addrs = socket.gethostbyaddr(ip)
                if host and host != ip:
                    holder["name"] = host
            except Exception:
                holder["name"] = ""

        thread = threading.Thread(target=worker, daemon=True)
        thread.start()
        thread.join(timeout_s)
        return holder["name"]

    # ------------------------------------------------------------------
    # 内部工具
    # ------------------------------------------------------------------
    def _resolve_probe_ports(self, config: Dict[str, Any]) -> List[int]:
        """解析实际探测端口：开启端口探测且有合法端口时用传入列表，否则用默认判活端口"""
        cleaned: List[int] = []
        for raw in config.get("ports") or []:
            try:
                port = int(raw)
            except (TypeError, ValueError):
                continue
            if 1 <= port <= 65535 and port not in cleaned:
                cleaned.append(port)
        if config.get("port_scan") and cleaned:
            return cleaned
        return list(DEFAULT_PROBE_PORTS)

    def _progress_payload(self, task: Dict[str, Any]) -> Dict[str, Any]:
        """构造 progress 事件体"""
        total = task["total"]
        online = task["online"]
        offline = task["offline"]
        occupied = online + offline
        return {
            "type": "progress",
            "task_id": task["task_id"],
            "scanned": task["scanned"],
            "total": total,
            "online": online,
            "offline": offline,
            "occupied": occupied,
            "utilization": round(occupied * 100 / total, 2) if total else 0,
            "cidr": task.get("cidr") or "",
            "elapsed": self._elapsed(task),
        }

    def _enqueue(self, task: Dict[str, Any], event: Dict[str, Any]) -> None:
        """线程安全入队"""
        with self._lock:
            task["queue"].append(event)

    @staticmethod
    def _elapsed(task: Dict[str, Any]) -> float:
        """已耗时（秒），任务结束后固定为总耗时"""
        end = task.get("finished_at") or time.time()
        return round(end - task["started_at"], 2)

    @staticmethod
    def _utilization(task: Dict[str, Any]) -> float:
        """IP 占用率（已发现设备 / 扫描总地址）"""
        total = task.get("total") or 0
        occupied = (task.get("online") or 0) + (task.get("offline") or 0)
        return round(occupied * 100 / total, 2) if total else 0

    @staticmethod
    def _sort_items(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """按 IPv4 数值自然排序"""

        def key(item: Dict[str, Any]):
            try:
                return tuple(int(part) for part in item["ip"].split("."))
            except Exception:
                return (999, 999, 999, 999)

        return sorted(items, key=key)

    @staticmethod
    def _clamp_int(value: Any, default: int, low: int, high: int) -> int:
        """把输入规整到 [low, high] 区间，非法值取默认"""
        try:
            number = int(value)
        except (TypeError, ValueError):
            number = default
        return max(low, min(high, number))

    def _prune_tasks_locked(self) -> None:
        """清理过多的历史任务（调用方需持有 self._lock）"""
        if len(self._tasks) <= MAX_KEPT_TASKS:
            return
        ordered = sorted(self._tasks.values(), key=lambda item: item["started_at"])
        for task in ordered:
            if len(self._tasks) <= MAX_KEPT_TASKS:
                break
            if task["task_id"] == self._current_task_id:
                continue
            if task["status"] in _TERMINAL_STATUS:
                self._tasks.pop(task["task_id"], None)


# 实例化扫描管理器
scan_manager = ScanManager()


# ----------------------------------------------------------------------
# CSV 导出（供路由复用，UTF-8 带 BOM 便于 Excel 直接打开）
# ----------------------------------------------------------------------
_CSV_HEADER = ["状态", "IP 地址", "MAC 地址", "厂商", "主机名", "延迟(ms)", "开放端口", "备注"]


def export_csv(
    items: List[Dict[str, Any]], directory: str = "", filename: str = ""
) -> Dict[str, Any]:
    """
    将扫描结果写为 CSV 文件。

    Args:
        items: 结果项列表（可含 ``note`` 字段）
        directory: 目标目录；为空则使用当前工作目录
        filename: 文件名；为空则自动生成 ``scan_result_<时间>.csv``

    Returns:
        ``{"path", "count", "size"}``
    """
    target_dir = (directory or "").strip() or os.getcwd()
    os.makedirs(target_dir, exist_ok=True)

    name = (filename or "").strip()
    if not name:
        name = f"scan_result_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    elif not name.lower().endswith(".csv"):
        name += ".csv"

    path = os.path.join(target_dir, name)
    with open(path, "w", encoding="utf-8-sig", newline="") as file:
        writer = csv.writer(file)
        writer.writerow(_CSV_HEADER)
        for item in items:
            ports = item.get("ports") or []
            ports_text = " ".join(str(port) for port in ports)
            writer.writerow(
                [
                    "在线" if item.get("online") else "离线",
                    item.get("ip", ""),
                    item.get("mac", ""),
                    item.get("vendor", ""),
                    item.get("hostname", ""),
                    item.get("delay_ms", 0),
                    ports_text,
                    item.get("note", ""),
                ]
            )

    return {"path": path, "count": len(items), "size": os.path.getsize(path)}
