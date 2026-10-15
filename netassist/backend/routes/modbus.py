"""
Modbus 路由：帧拼装
"""
from fastapi import APIRouter, HTTPException
from models import ModbusBuildRequest
from services.modbus_service import build_modbus_frame

router = APIRouter(prefix="/api/modbus", tags=["Modbus"])


@router.post("/build")
async def modbus_build(request: ModbusBuildRequest):
    """拼装 Modbus 帧（RTU / TCP / ASCII）"""
    try:
        result = build_modbus_frame(
            protocol=request.protocol,
            slave_id=request.slave_id,
            function=request.function,
            address=request.address,
            quantity=request.quantity,
            values=request.values,
            byte_order=request.byte_order,
        )
        return {
            "success": True,
            "data": {
                "frame_hex": result["frame_hex"],
                "length": result["length"],
                "protocol": result["protocol"],
            },
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
