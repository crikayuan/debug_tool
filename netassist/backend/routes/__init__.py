# 使routes目录成为Python包
from .serial import router as serial_router
from .websocket import router as websocket_router
from .system import router as system_router
from .net import router as net_router
from .scan import router as scan_router

__all__ = [
    "serial_router",
    "websocket_router",
    "system_router",
    "net_router",
    "scan_router",
]