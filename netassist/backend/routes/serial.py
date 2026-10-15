"""
串口相关路由
"""
from fastapi import APIRouter, HTTPException
from models import SerialConfig, SendDataRequest
from services.serial_service import serial_manager
from utils.data_utils import format_data_for_send

router = APIRouter(prefix="/api/serial", tags=["Serial"])


@router.get("/ports")
async def get_serial_ports():
    """获取可用串口列表"""
    result = serial_manager.get_available_ports()
    return result.dict()


@router.post("/connect")
async def serial_connect(config: SerialConfig):
    """打开串口连接"""
    result = serial_manager.create_connection(config)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.dict()


@router.post("/disconnect/{port:path}")
async def serial_disconnect(port: str):
    """关闭串口连接"""
    result = serial_manager.disconnect(port)
    if not result.success:
        raise HTTPException(status_code=404, detail=result.message)
    return result.dict()


@router.post("/send/{port:path}")
async def serial_send_data(port: str, request: SendDataRequest):
    """发送串口数据"""
    try:
        data = format_data_for_send(
            request.data,
            request.format,
            request.encoding,
            request.end_chars,
            request.append_check,
        )
        result = serial_manager.send_data(port, data)

        if not result.success:
            raise HTTPException(status_code=404, detail=result.message)

        return result.dict()

    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"数据格式错误: {str(e)}")
    except Exception as e:
        print(f"串口发送数据异常: {str(e)}")
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")


@router.get("/status/{port:path}")
async def serial_get_status(port: str):
    """获取串口连接状态"""
    status = serial_manager.get_connection_status(port)
    if status is None:
        return {"connected": False}
    return status
