"""
网络扫描相关路由（prefix=/api/scan）。

接口表（详见 `docs/网络扫描模块设计方案.md` §4.2）：
- GET  /segments             本机可用网段（有线优先，含网卡类型标签）
- POST /start                启动扫描，返回 task_id
- POST /stop/{task_id}       停止扫描
- GET  /result/{task_id}     全量结果（供前端刷新后恢复）
- POST /export               导出 CSV（UTF-8 带 BOM）

WebSocket 进度与结果推送见 `routes/websocket.py` 的 ``/ws/scan/{task_id}``。
备注/收藏等持久化复用现有 ``/api/store``（key = na_scan_notes / na_scan_favorites）。
"""

import ipaddress
import logging
import socket

import psutil
from fastapi import APIRouter, HTTPException

from models import APIResponse, ScanConfig, ScanExportRequest
from services.scan_service import export_csv, scan_manager
from utils.netif_utils import (
    RANK_LABELS,
    RANK_LOOPBACK,
    _ip_sort_key,
    _windows_iface_types,
    classify_ip,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/scan", tags=["网络扫描"])


@router.get("/segments")
async def scan_segments():
    """
    返回本机可用网段列表（复用 netif_utils 网卡分类，有线优先）。

    Returns:
        ``{"success": True, "data": {"segments": [{cidr, ip, netmask, interface, type, rank, host_count}]}}``
    """
    try:
        iftypes = _windows_iface_types()
    except Exception:
        iftypes = {}

    try:
        interfaces = psutil.net_if_addrs()
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"读取网卡信息失败: {str(exc)}")

    segments = []
    seen_cidr = set()

    for iface, addrs in interfaces.items():
        iftype, desc = iftypes.get((iface or "").lower(), (None, ""))
        for addr in addrs:
            if addr.family != socket.AF_INET:
                continue

            ip = addr.address
            netmask = getattr(addr, "netmask", None)
            if not netmask:
                continue
            # 过滤 APIPA 链路本地地址与回环
            if ip.startswith("169.254.") or ip.startswith("127."):
                continue

            rank = classify_ip(iface, ip, iftype, desc)
            if rank == RANK_LOOPBACK:
                continue

            try:
                network = ipaddress.ip_network(f"{ip}/{netmask}", strict=False)
            except Exception:
                continue

            cidr = str(network)
            if cidr in seen_cidr:
                continue
            seen_cidr.add(cidr)

            host_count = (
                network.num_addresses - 2
                if network.num_addresses > 2
                else network.num_addresses
            )
            segments.append(
                {
                    "cidr": cidr,
                    "ip": ip,
                    "netmask": netmask,
                    "interface": iface,
                    "type": RANK_LABELS.get(rank, "其他"),
                    "rank": rank,
                    "host_count": max(0, host_count),
                }
            )

    # 有线 → 无线 → 虚拟 → 其他；同类别按 IP 数值排序
    segments.sort(key=lambda seg: (seg["rank"], _ip_sort_key(seg["ip"])))
    return {"success": True, "data": {"segments": segments}}


@router.post("/start")
async def scan_start(config: ScanConfig):
    """启动扫描，返回 task_id"""
    result = scan_manager.start(config)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.dict()


@router.post("/stop/{task_id}")
async def scan_stop(task_id: str):
    """停止扫描（已完成结果保留）"""
    result = scan_manager.stop(task_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result.dict()


@router.get("/result/{task_id}")
async def scan_result(task_id: str):
    """获取全量结果（供前端刷新后恢复）"""
    data = scan_manager.get_result(task_id)
    if data is None:
        raise HTTPException(status_code=404, detail="扫描任务不存在")
    return {"success": True, "data": data}


@router.post("/export")
async def scan_export(request: ScanExportRequest):
    """
    导出扫描结果为 CSV（UTF-8 带 BOM，便于 Excel 直接打开）。

    优先使用请求体携带的 items（含前端合并的备注）；items 为空时回退到 task_id 的服务端结果。
    """
    items = [item.model_dump() for item in request.items]

    if not items and request.task_id:
        data = scan_manager.get_result(request.task_id)
        if data is None:
            raise HTTPException(status_code=404, detail="扫描任务不存在")
        items = data.get("items", [])

    if not items:
        raise HTTPException(status_code=400, detail="没有可导出的扫描结果")

    try:
        info = export_csv(items, request.directory, request.filename)
    except Exception as exc:
        logger.exception("导出 CSV 失败")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(exc)}")

    return APIResponse(success=True, message="导出成功", data=info).dict()
