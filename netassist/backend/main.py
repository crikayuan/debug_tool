"""
网络调试助手后端API - 主入口文件
优化后的模块化结构，集成前端静态文件
"""

import sys
import os
from pathlib import Path
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from config import settings
from routes.serial import router as serial_router
from routes.websocket import router as websocket_router
from routes.system import router as system_router
from routes.net import router as net_router
from routes.toolbox import router as toolbox_router
from routes.modbus import router as modbus_router
from routes.log import router as log_router
from routes.store import router as store_router
from routes.mqtt import router as mqtt_router
from routes.scan import router as scan_router
from routes.http_server import router as http_server_router


def get_static_path():
    """获取静态文件路径，支持PyInstaller打包"""
    if getattr(sys, "frozen", False):
        # 单文件模式：静态文件在 _MEIPASS 临时解压目录
        meipass = getattr(sys, "_MEIPASS", None)
        base_path = Path(meipass) if meipass else (Path(sys.executable).parent / "_internal")
        static_path = base_path / "static"
    else:
        # 开发环境路径
        base_path = Path(__file__).parent
        static_path = base_path / settings.STATIC_DIR

    return static_path


def get_index_file_path():
    """获取index.html文件路径"""
    static_path = get_static_path()
    return static_path / "index.html"


# 创建FastAPI应用实例
app = FastAPI(
    title=settings.APP_NAME,
    version=settings.VERSION,
    description="网络调试助手后端API - 支持TCP/UDP和串口通信，集成Web界面",
)

# 添加CORS中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=settings.CORS_ALLOW_CREDENTIALS,
    allow_methods=settings.CORS_ALLOW_METHODS,
    allow_headers=settings.CORS_ALLOW_HEADERS,
)

# 注册路由
app.include_router(serial_router)
app.include_router(websocket_router)
app.include_router(system_router)
app.include_router(net_router)
app.include_router(toolbox_router)
app.include_router(modbus_router)
app.include_router(log_router)
app.include_router(store_router)
# MQTT 路由必须在下方 /{path:path} catch-all 之前注册，否则被 SPA 兜底吞掉
app.include_router(mqtt_router)
# 网络扫描路由同样必须在 /{path:path} catch-all 之前注册
app.include_router(scan_router)
# HTTP Server 路由同样必须在 /{path:path} catch-all 之前注册
app.include_router(http_server_router)

# 挂载静态文件服务（前端文件）
static_path = get_static_path()
if static_path.exists():
    # 挂载静态文件目录到/static路径
    app.mount("/static", StaticFiles(directory=str(static_path)), name="static")

    # 单独挂载assets目录到/assets路径（如果存在）
    assets_path = static_path / "assets"
    if assets_path.exists():
        app.mount("/assets", StaticFiles(directory=str(assets_path)), name="assets")
        print(f"Assets路径: {assets_path}")

    print(f"静态文件路径: {static_path}")
else:
    print(f"警告: 静态文件目录不存在: {static_path}")


@app.get("/")
async def root():
    """根路径 - 返回前端页面或API信息"""
    # 如果静态文件存在，返回前端页面
    index_file = get_index_file_path()
    if index_file.exists():
        return FileResponse(str(index_file))

    # 否则返回API信息
    return {
        "message": settings.APP_NAME,
        "version": settings.VERSION,
        "docs": "/docs",
        "health": "ok",
        "frontend": "not_available",
        "static_path": str(get_static_path()),
    }


@app.get("/health")
async def health_check():
    """健康检查端点"""
    return {"status": "healthy", "version": settings.VERSION}


@app.get("/{path:path}")
async def catch_all(path: str):
    """捕获所有路由，用于SPA路由支持"""
    # 对于静态资源文件，尝试返回文件
    static_path = get_static_path()
    file_path = static_path / path
    if file_path.exists() and file_path.is_file():
        return FileResponse(str(file_path))

    # 其他路径都返回index.html（SPA路由支持）
    index_file = get_index_file_path()
    if index_file.exists():
        return FileResponse(str(index_file))

    # 如果连index.html都没有，返回404
    from fastapi import HTTPException

    raise HTTPException(status_code=404, detail="页面未找到")


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(
        "main:app",  # 使用导入字符串而不是直接传递app对象
        host=settings.HOST,
        port=settings.PORT,
    )
