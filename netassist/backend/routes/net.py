"""
网络相关路由 - 支持TCP和UDP，含 TCP Server 客户端管理与定向发送
"""
from fastapi import APIRouter, HTTPException
from models import NetConfig, SendDataRequest
from services.net_service import net_manager
from utils.data_utils import format_data_for_send

router = APIRouter(prefix="/api/net", tags=["网络"])


@router.post("/connect")
async def net_connect(config: NetConfig):
    """建立网络连接"""
    result = net_manager.create_connection(config)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.dict()


@router.post("/disconnect/{connection_id}")
async def net_disconnect(connection_id: str):
    """断开网络连接"""
    result = net_manager.disconnect(connection_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result.dict()


@router.post("/send/{connection_id}")
async def net_send_data(connection_id: str, request: SendDataRequest):
    """发送网络数据（支持定向发送）"""
    try:
        data = format_data_for_send(
            request.data,
            request.format,
            request.encoding,
            request.end_chars,
            request.append_check,
        )
        result = net_manager.send_data(connection_id, data, request.target)

        if not result.success:
            raise HTTPException(status_code=404, detail=result.message)

        return result.dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"数据格式错误: {str(e)}")
    except Exception as e:
        print(f"网络发送数据异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


@router.get("/status/{connection_id}")
async def net_get_status(connection_id: str):
    """获取网络连接状态"""
    status = net_manager.get_connection_status(connection_id)
    if status is None:
        return {"connected": False}
    return status


@router.get("/clients/{connection_id}")
async def net_get_clients(connection_id: str):
    """获取 TCP Server 已连接客户端列表"""
    clients = net_manager.get_clients(connection_id)
    return {"success": True, "data": {"clients": clients}}


@router.post("/client/{connection_id}/disconnect/{client_id}")
async def net_disconnect_client(connection_id: str, client_id: str):
    """断开 TCP Server 的单个客户端"""
    result = net_manager.disconnect_client(connection_id, client_id)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result.dict()
