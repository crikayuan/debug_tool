"""
系统配置相关路由
"""
from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse
from models import PortConfigRequest, PortConfigResponse, APIResponse
from config import settings
import os
import signal

router = APIRouter(prefix="/api/system", tags=["System"])

@router.get("/config/port", response_model=PortConfigResponse)
async def get_port_config():
    """获取当前端口配置"""
    return PortConfigResponse(
        current_port=settings.PORT,
        host=settings.HOST
    )

@router.post("/config/port")
async def update_port_config(request: PortConfigRequest):
    """更新端口配置"""
    if not (1 <= request.port <= 65535):
        raise HTTPException(
            status_code=400, 
            detail="端口号必须在1-65535范围内"
        )
    
    # 检查端口是否被占用
    import socket
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        result = sock.connect_ex((settings.HOST, request.port))
        sock.close()
        
        if result == 0 and request.port != settings.PORT:
            raise HTTPException(
                status_code=400,
                detail=f"端口 {request.port} 已被占用"
            )
    except Exception:
        pass
    
    # 更新配置
    if settings.update_port(request.port):
        return APIResponse(
            success=True,
            message=f"端口配置已更新为 {request.port}，需要重启服务生效",
            data={
                "old_port": settings.PORT,
                "new_port": request.port,
                "restart_required": True
            }
        )
    else:
        raise HTTPException(
            status_code=500,
            detail="保存配置失败"
        )

@router.post("/restart")
async def restart_service():
    """重启服务（仅在systemd管理下有效）"""
    try:
        # 发送重启信号
        os.kill(os.getpid(), signal.SIGUSR1)
        return APIResponse(
            success=True,
            message="正在重启服务..."
        )
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"重启失败: {str(e)}"
        )

@router.get("/info")
async def get_system_info():
    """获取系统信息"""
    import platform
    import psutil
    
    return {
        "system": {
            "platform": platform.platform(),
            "python_version": platform.python_version(),
            "architecture": platform.architecture()[0]
        },
        "service": {
            "name": settings.APP_NAME,
            "version": settings.VERSION,
            "host": settings.HOST,
            "port": settings.PORT
        },
        "resources": {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_percent": psutil.disk_usage('/').percent
        }
    }


@router.get("/interfaces")
async def get_interfaces():
    """
    获取本机 IPv4 地址列表（供 Server 模式监听地址下拉选择）。

    排序规则：0.0.0.0 → 有线网 IP → 无线网 IP → 虚拟网卡 IP → 回环 IP → 其他
    """
    import socket

    import psutil

    from utils.netif_utils import (
        RANK_LABELS,
        RANK_WIRED,
        RANK_WIRELESS,
        _windows_iface_types,
        classify_ip,
        sort_local_ips,
    )

    iftypes = _windows_iface_types()

    entries = []       # [(ip, rank)]
    labels = {}        # {ip: 分类中文名}
    seen = set()
    for iface, addrs in psutil.net_if_addrs().items():
        iftype, desc = iftypes.get(iface.lower(), (None, ""))
        for a in addrs:
            if a.family != socket.AF_INET:
                continue
            ip = a.address
            # 过滤 APIPA 链路本地地址（169.254.x.x，无有效网络）
            if ip.startswith("169.254.") or ip in seen:
                continue
            seen.add(ip)
            rank = classify_ip(iface, ip, iftype, desc)
            entries.append((ip, rank))
            labels.setdefault(ip, RANK_LABELS.get(rank, "其他"))

    ordered = sort_local_ips(entries)

    # 0.0.0.0 = 监听全部网卡，固定在最前
    result = list(dict.fromkeys(["0.0.0.0"] + ordered))

    # 默认选中：优先第一个有线 IP，其次第一个无线 IP
    preferred = ""
    for rank in (RANK_WIRED, RANK_WIRELESS):
        for ip, r in entries:
            if r == rank:
                preferred = ip
                break
        if preferred:
            break

    return {
        "success": True,
        "data": {"ips": result, "labels": labels, "preferred": preferred},
    }