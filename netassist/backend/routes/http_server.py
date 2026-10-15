"""
HTTP Server 相关路由（prefix=/api/http-server）。

接口表（详见 `docs/HTTP_Server模块设计方案.md` §4.2）：
- POST /start          启动 HTTP 服务端，返回 session_id 与可用访问地址
- POST /stop           停止服务端
- GET  /status         状态快照（含 addresses，供前端展示/复制访问 URL）
- GET  /requests       全量请求记录（供前端刷新后恢复）
- POST /clear          清空请求记录
- POST /response       更新响应配置（状态码/Content-Type/body/延迟/echo）
- POST /export         导出请求日志文本

WebSocket 实时请求推送见 `routes/websocket.py` 的 ``/ws/http/{session_id}``。
"""

import logging

from fastapi import APIRouter, HTTPException

from models import APIResponse, HttpExportRequest, HttpServerConfig
from services.http_server_service import export_records, http_server_manager

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/http-server", tags=["HTTP Server"])


@router.post("/start")
async def http_server_start(config: HttpServerConfig):
    """
    启动 HTTP 服务端。

    Returns:
        ``{"success": True, "data": {"session_id", "port", "bind", "addresses"}}``
    """
    result = http_server_manager.start(config)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.dict()


@router.post("/stop")
async def http_server_stop():
    """停止 HTTP 服务端（已记录的请求保留）"""
    result = http_server_manager.stop()
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.dict()


@router.get("/status")
async def http_server_status():
    """获取服务端状态快照（含所有可用访问地址）"""
    return {"success": True, "data": http_server_manager.status()}


@router.get("/requests")
async def http_server_requests():
    """获取全量请求记录（供前端刷新后恢复）"""
    records = http_server_manager.get_records()
    return {"success": True, "data": {"records": records, "count": len(records)}}


@router.post("/clear")
async def http_server_clear():
    """清空请求记录"""
    result = http_server_manager.clear()
    return result.dict()


@router.post("/response")
async def http_server_set_response(payload: dict):
    """更新响应配置（运行中实时生效）"""
    result = http_server_manager.set_response_config(payload or {})
    return result.dict()


@router.post("/export")
async def http_server_export(request: HttpExportRequest):
    """
    导出请求记录为日志文本（UTF-8 带 BOM）。

    记录取自服务端内存（导出即当前全部记录）。
    """
    records = http_server_manager.get_records()
    if not records:
        raise HTTPException(status_code=400, detail="没有可导出的请求记录")

    try:
        info = export_records(records, request.directory, request.filename)
    except Exception as exc:
        logger.exception("导出 HTTP 请求日志失败")
        raise HTTPException(status_code=500, detail=f"导出失败: {str(exc)}")

    return APIResponse(success=True, message="导出成功", data=info).dict()
