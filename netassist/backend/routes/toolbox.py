"""
工具箱路由：校验计算、数据转换
"""
from fastapi import APIRouter, HTTPException
from models import CheckRequest, ConvertRequest
from utils.check_utils import compute_check_hex, ALGORITHMS
from utils.data_utils import (
    convert_hex_to_text,
    convert_text_to_hex,
    validate_hex_string,
    _encode_text,
)

router = APIRouter(prefix="/api/toolbox", tags=["工具箱"])


@router.post("/check")
async def toolbox_check(request: CheckRequest):
    """校验计算"""
    try:
        if request.format == "hex":
            cleaned = "".join(request.data.split())
            if not validate_hex_string(cleaned):
                raise ValueError("无效的十六进制数据")
            raw = bytes.fromhex(cleaned)
        else:
            raw = _encode_text(request.data, "utf-8")

        hex_value = compute_check_hex(request.algorithm, raw)
        return {"success": True, "data": {"hex": hex_value, "length": len(raw)}}
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.post("/convert")
async def toolbox_convert(request: ConvertRequest):
    """数据转换：hex <-> text"""
    try:
        if request.from_format == "hex" and request.to_format == "text":
            text = convert_hex_to_text(request.data, request.encoding)
            return {"success": True, "data": {"result": text}}
        elif request.from_format == "text" and request.to_format == "hex":
            hex_str = convert_text_to_hex(request.data, request.encoding)
            return {"success": True, "data": {"result": hex_str}}
        else:
            raise ValueError("不支持的转换方向")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))


@router.get("/algorithms")
async def toolbox_algorithms():
    """获取支持的校验算法列表"""
    return {"success": True, "data": {"algorithms": list(ALGORITHMS.keys())}}
