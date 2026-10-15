"""
本地数据持久化路由：快捷指令等用户数据的永久存储
"""
from typing import Any, Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from services import store_service

router = APIRouter(prefix="/api/store", tags=["数据存储"])


class StorePutRequest(BaseModel):
    value: Any


@router.get("/path")
async def store_path():
    """返回数据文件实际路径，便于排查"""
    return {"success": True, "data": {"path": store_service.get_store_path()}}


@router.get("/{key}")
async def store_get(key: str):
    """读取指定键的数据（不存在返回 null）"""
    try:
        return {"success": True, "data": {"key": key, "value": store_service.get(key)}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"读取数据失败: {str(e)}")


@router.put("/{key}")
async def store_put(key: str, request: StorePutRequest):
    """写入指定键的数据"""
    try:
        store_service.set_value(key, request.value)
        return {"success": True, "data": {"key": key}}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存数据失败: {str(e)}")
