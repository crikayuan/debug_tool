"""
日志路由：写盘
"""
from fastapi import APIRouter, HTTPException
from models import LogSaveRequest
from services.log_service import save_log

router = APIRouter(prefix="/api/log", tags=["日志"])


@router.post("/save")
async def log_save(request: LogSaveRequest):
    """保存日志到文件（追加模式）"""
    try:
        result = save_log(
            request.filename, request.directory, request.content, request.encoding
        )
        return {"success": True, "data": result}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"保存日志失败: {str(e)}")
