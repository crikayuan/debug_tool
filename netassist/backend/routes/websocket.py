"""
WebSocket相关路由
网络端点支持 TCP Server 多客户端来源标识（client_id）
接收编码通过 URL query 参数 encoding 指定
"""

import asyncio
import json
import time
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from services.net_service import net_manager
from services.serial_service import serial_manager
from services.mqtt_service import mqtt_manager
from services.scan_service import scan_manager
from services.http_server_service import http_server_manager
from utils.data_utils import format_received_data
from config import settings

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws/net/{connection_id}")
async def net_websocket_endpoint(
    websocket: WebSocket, connection_id: str, encoding: str = "utf-8"
):
    """网络WebSocket端点，用于实时数据传输(支持TCP和UDP)"""
    await websocket.accept()

    last_data_time = time.time()
    heartbeat_interval = 1.0
    check_data_interval = 0.05  # 50ms，提升吞吐
    connection_timeout = settings.WEBSOCKET_TIMEOUT

    try:
        while True:
            current_time = time.time()

            connection = net_manager.get_connection(connection_id)
            if not connection:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "message": "连接不存在", "timestamp": current_time}
                    )
                )
                break

            if current_time - last_data_time > connection_timeout:
                logger.warning(f"WebSocket连接超时: {connection_id}")
                break

            # 读取数据：返回 (client_id, data) 元组
            result = await asyncio.to_thread(net_manager.read_data, connection_id)
            if result:
                client_id, data = result
                formatted_data = format_received_data(data, encoding)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "data",
                            "connection_id": connection_id,
                            "client_id": client_id,
                            "data": formatted_data["text"],
                            "hex_data": formatted_data["hex"],
                            "length": formatted_data["length"],
                            "timestamp": current_time,
                        }
                    )
                )
                last_data_time = current_time
            else:
                if current_time - last_data_time >= heartbeat_interval:
                    clients = net_manager.get_clients(connection_id)
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "heartbeat",
                                "data": {
                                    "connectionId": connection_id,
                                    "status": (
                                        "connected"
                                        if connection["connected"]
                                        else "disconnected"
                                    ),
                                    "protocol": connection["config"].get("protocol", "tcp"),
                                    "host": connection["config"].get("host", ""),
                                    "port": connection["config"].get("port", 0),
                                    "stats": connection["stats"],
                                    "clients": clients,
                                },
                                "timestamp": current_time,
                            }
                        )
                    )
                    last_data_time = current_time

            await asyncio.sleep(check_data_interval)

    except WebSocketDisconnect:
        logger.info(f"WebSocket连接已断开: {connection_id}")
    except asyncio.CancelledError:
        logger.info(f"WebSocket任务已取消: {connection_id}")
    except Exception as e:
        logger.error(f"WebSocket错误: {str(e)}")
        try:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"WebSocket错误: {str(e)}", "timestamp": time.time()}
                )
            )
        except Exception:
            pass
    finally:
        logger.info(f"WebSocket资源已清理: {connection_id}")


@router.websocket("/ws/mqtt/{connection_id}")
async def mqtt_websocket_endpoint(
    websocket: WebSocket, connection_id: str, encoding: str = "utf-8"
):
    """MQTT WebSocket端点，用于实时消息推送（50ms 轮询 + 1s heartbeat，与 net 端点同构）"""
    await websocket.accept()

    last_data_time = time.time()
    heartbeat_interval = 1.0
    check_data_interval = 0.05  # 50ms，与 /ws/net 一致
    connection_timeout = settings.WEBSOCKET_TIMEOUT

    try:
        while True:
            current_time = time.time()

            connection = mqtt_manager.get_connection(connection_id)
            if not connection:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "message": "连接不存在", "timestamp": current_time}
                    )
                )
                break

            if current_time - last_data_time > connection_timeout:
                logger.warning(f"MQTT WebSocket连接超时: {connection_id}")
                break

            # 读取数据：返回 (topic, payload_bytes, qos, retain) 四元组
            result = await asyncio.to_thread(mqtt_manager.read_data, connection_id)
            if result:
                topic, payload, qos, retain = result
                formatted_data = format_received_data(payload, encoding)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "data",
                            "connection_id": connection_id,
                            "topic": topic,
                            "data": formatted_data["text"],
                            "hex_data": formatted_data["hex"],
                            "qos": qos,
                            "retain": retain,
                            "length": formatted_data["length"],
                            "timestamp": current_time,
                        }
                    )
                )
                last_data_time = current_time
            else:
                if current_time - last_data_time >= heartbeat_interval:
                    status = mqtt_manager.get_status(connection_id) or {}
                    await websocket.send_text(
                        json.dumps(
                            {
                                "type": "heartbeat",
                                "data": {
                                    "connectionId": connection_id,
                                    "status": (
                                        "connected"
                                        if status.get("connected")
                                        else "disconnected"
                                    ),
                                    "host": status.get("host", ""),
                                    "port": status.get("port", 0),
                                    "clientId": status.get("client_id", ""),
                                    "stats": status.get("stats", {}),
                                    "subscriptions": status.get("subscriptions", []),
                                },
                                "timestamp": current_time,
                            }
                        )
                    )
                    last_data_time = current_time

            await asyncio.sleep(check_data_interval)

    except WebSocketDisconnect:
        logger.info(f"MQTT WebSocket连接已断开: {connection_id}")
    except asyncio.CancelledError:
        logger.info(f"MQTT WebSocket任务已取消: {connection_id}")
    except Exception as e:
        logger.error(f"MQTT WebSocket错误: {str(e)}")
        try:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"WebSocket错误: {str(e)}", "timestamp": time.time()}
                )
            )
        except Exception:
            pass
    finally:
        logger.info(f"MQTT WebSocket资源已清理: {connection_id}")


@router.websocket("/ws/scan/{task_id}")
async def scan_websocket_endpoint(websocket: WebSocket, task_id: str):
    """
    网络扫描 WebSocket 端点（50ms 轮询 + 1s heartbeat，与 /ws/net 同构）。

    数据帧（详见设计文档 §4.2）：
    - {"type":"progress","task_id":..,"scanned":..,"total":..,"online":..,"elapsed":..}
    - {"type":"result","task_id":..,"item":{ip,mac,vendor,hostname,delay_ms,ports,online}}
    - {"type":"done","task_id":..,"scanned":..,"online":..,"elapsed":..,"status":"done|stopped"}
    另外：无数据时按 heartbeat_interval 推送 {"type":"heartbeat",...} 保活。

    说明：单次轮询会把队列中所有事件一次性批量下发，避免 50ms/条 造成的推送积压。
    """
    await websocket.accept()

    last_data_time = time.time()
    heartbeat_interval = 1.0
    check_data_interval = 0.05  # 50ms，与 /ws/net 一致
    connection_timeout = settings.WEBSOCKET_TIMEOUT

    try:
        while True:
            current_time = time.time()

            task = scan_manager.get_task(task_id)
            if not task:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "message": "扫描任务不存在", "timestamp": current_time}
                    )
                )
                break

            if current_time - last_data_time > connection_timeout:
                logger.warning(f"扫描 WebSocket连接超时: {task_id}")
                break

            # 批量下发队列中的全部事件（progress / result / done）
            got_any = False
            terminal = False
            while True:
                event = await asyncio.to_thread(scan_manager.read_event, task_id)
                if event is None:
                    break
                await websocket.send_text(json.dumps(event, ensure_ascii=False))
                last_data_time = time.time()
                got_any = True
                if event.get("type") == "done":
                    terminal = True
                    break

            if terminal:
                logger.info(f"扫描任务已完成，关闭 WebSocket: {task_id}")
                break

            # 任务已结束且队列已排空（如前端在扫描结束后才连上）：补发一次终态帧后关闭
            if not got_any and task.get("status") in ("done", "stopped", "error"):
                progress = await asyncio.to_thread(scan_manager.get_progress, task_id) or {}
                result = await asyncio.to_thread(scan_manager.get_result, task_id) or {}
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "done",
                            "task_id": task_id,
                            "scanned": progress.get("scanned", task.get("scanned", 0)),
                            "online": progress.get("online", task.get("online", 0)),
                            "offline": progress.get("offline", task.get("offline", 0)),
                            "occupied": progress.get("occupied", 0),
                            "utilization": progress.get("utilization", 0),
                            "cidr": progress.get("cidr", ""),
                            "changes": result.get("changes") or {"new": [], "left": [], "changed": []},
                            "elapsed": progress.get("elapsed", 0),
                            "status": task.get("status"),
                            "replay": True,
                        },
                        ensure_ascii=False,
                    )
                )
                break

            if not got_any and (time.time() - last_data_time >= heartbeat_interval):
                progress = await asyncio.to_thread(scan_manager.get_progress, task_id)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "heartbeat",
                            "task_id": task_id,
                            "data": progress or {},
                            "timestamp": time.time(),
                        },
                        ensure_ascii=False,
                    )
                )
                last_data_time = time.time()

            await asyncio.sleep(check_data_interval)

    except WebSocketDisconnect:
        logger.info(f"扫描 WebSocket连接已断开: {task_id}")
    except asyncio.CancelledError:
        logger.info(f"扫描 WebSocket任务已取消: {task_id}")
    except Exception as e:
        logger.error(f"扫描 WebSocket错误: {str(e)}")
        try:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"WebSocket错误: {str(e)}", "timestamp": time.time()}
                )
            )
        except Exception:
            pass
    finally:
        logger.info(f"扫描 WebSocket资源已清理: {task_id}")


@router.websocket("/ws/http/{session_id}")
async def http_server_websocket_endpoint(websocket: WebSocket, session_id: str):
    """
    HTTP Server 实时请求推送端点。

    说明：单次轮询批量下发队列中所有记录，避免 50ms/条 造成推送积压。
    前端连接后停留在此 WS，服务端每收到一个 HTTP 请求就立即推到界面。
    """
    await websocket.accept()

    last_data_time = time.time()
    heartbeat_interval = 1.0
    check_data_interval = 0.05  # 50ms，与其他端点一致

    try:
        while True:
            current_time = time.time()

            if not http_server_manager.is_running():
                await websocket.send_text(
                    json.dumps(
                        {"type": "closed", "message": "HTTP 服务已停止", "timestamp": current_time}
                    )
                )
                break

            if http_server_manager.get_session_id() != session_id:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "message": "会话已失效", "timestamp": current_time}
                    )
                )
                break

            got_any = False
            while True:
                record = await asyncio.to_thread(http_server_manager.read_event)
                if record is None:
                    break
                await websocket.send_text(
                    json.dumps({"type": "request", "data": record}, ensure_ascii=False)
                )
                last_data_time = time.time()
                got_any = True

            if not got_any and (time.time() - last_data_time >= heartbeat_interval):
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "heartbeat",
                            "data": {
                                "total": http_server_manager.status().get("total", 0),
                                "running": http_server_manager.is_running(),
                            },
                            "timestamp": time.time(),
                        }
                    )
                )
                last_data_time = time.time()

            await asyncio.sleep(check_data_interval)

    except WebSocketDisconnect:
        logger.info(f"HTTP Server WebSocket连接已断开: {session_id}")
    except asyncio.CancelledError:
        logger.info(f"HTTP Server WebSocket任务已取消: {session_id}")
    except Exception as e:
        logger.error(f"HTTP Server WebSocket错误: {str(e)}")
        try:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"WebSocket错误: {str(e)}", "timestamp": time.time()}
                )
            )
        except Exception:
            pass


@router.websocket("/ws/serial/{port:path}")
async def serial_websocket_endpoint(
    websocket: WebSocket, port: str, encoding: str = "utf-8"
):
    """串口WebSocket端点，用于实时数据传输"""
    await websocket.accept()

    try:
        while True:
            connection = serial_manager.get_connection(port)
            if not connection:
                await websocket.send_text(
                    json.dumps(
                        {"type": "error", "message": "串口连接不存在", "timestamp": time.time()}
                    )
                )
                break

            data = await asyncio.to_thread(serial_manager.read_data, port)
            if data:
                formatted_data = format_received_data(data, encoding)
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "data",
                            "port": port,
                            "data": formatted_data["text"],
                            "hex_data": formatted_data["hex"],
                            "length": formatted_data["length"],
                            "timestamp": time.time(),
                        }
                    )
                )
            else:
                await websocket.send_text(
                    json.dumps(
                        {
                            "type": "heartbeat",
                            "port": port,
                            "connected": connection["connected"],
                            "stats": connection["stats"],
                            "timestamp": time.time(),
                        }
                    )
                )

            await asyncio.sleep(settings.WEBSOCKET_PING_INTERVAL)

    except WebSocketDisconnect:
        pass
    except Exception as e:
        try:
            await websocket.send_text(
                json.dumps(
                    {"type": "error", "message": f"WebSocket错误: {str(e)}", "timestamp": time.time()}
                )
            )
        except Exception:
            pass
