"""
MQTT 相关路由 - 一期仅核心收发（连接 / 断开 / 订阅 / 取消订阅 / 发布 / 查询）

接口表（prefix=/api/mqtt，详见 `docs/设计-MQTT增量.md` §3.3）：
- POST /connect                    建立连接
- POST /disconnect/{connection_id} 断开连接
- POST /publish/{connection_id}    发布消息（复用 format_data_for_send）
- POST /subscribe/{connection_id}  订阅主题
- POST /unsubscribe/{connection_id} 取消订阅
- GET  /subscriptions/{connection_id} 查询订阅表
- GET  /status/{connection_id}     查询连接状态
"""
from fastapi import APIRouter, HTTPException

from models import (
    MqttConfig,
    MqttPublishRequest,
    MqttSubscribeRequest,
    MqttUnsubscribeRequest,
)
from services.mqtt_service import mqtt_manager
from utils.data_utils import format_data_for_send

router = APIRouter(prefix="/api/mqtt", tags=["MQTT"])


@router.post("/connect")
async def mqtt_connect(config: MqttConfig):
    """建立 MQTT 连接"""
    result = mqtt_manager.connect(config)
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    return result.dict()


@router.post("/disconnect/{connection_id}")
async def mqtt_disconnect(connection_id: str):
    """断开 MQTT 连接"""
    result = mqtt_manager.disconnect(connection_id)
    if not result.success:
        status = 404 if result.message == "连接不存在" else 400
        raise HTTPException(status_code=status, detail=result.message)
    return result.dict()


@router.post("/publish/{connection_id}")
async def mqtt_publish(connection_id: str, request: MqttPublishRequest):
    """发布 MQTT 消息（发送格式/结束符/校验复用 data_utils）"""
    try:
        payload = format_data_for_send(
            request.payload,
            request.format,
            request.encoding,
            request.end_chars,
            request.append_check,
        )
    except ValueError as e:
        raise HTTPException(status_code=400, detail=f"数据格式错误: {str(e)}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"内部服务器错误: {str(e)}")

    result = mqtt_manager.publish(
        connection_id, request.topic, payload, request.qos, request.retain
    )
    if not result.success:
        status = 404 if result.message == "连接不存在" else 400
        raise HTTPException(status_code=status, detail=result.message)
    return result.dict()


@router.post("/subscribe/{connection_id}")
async def mqtt_subscribe(connection_id: str, request: MqttSubscribeRequest):
    """订阅主题（支持 + / # 通配符）"""
    result = mqtt_manager.subscribe(connection_id, request.topic, request.qos)
    if not result.success:
        status = 404 if result.message == "连接不存在" else 400
        raise HTTPException(status_code=status, detail=result.message)
    return result.dict()


@router.post("/unsubscribe/{connection_id}")
async def mqtt_unsubscribe(connection_id: str, request: MqttUnsubscribeRequest):
    """取消订阅"""
    result = mqtt_manager.unsubscribe(connection_id, request.topic)
    if not result.success:
        status = 404 if result.message == "连接不存在" else 400
        raise HTTPException(status_code=status, detail=result.message)
    return result.dict()


@router.get("/subscriptions/{connection_id}")
async def mqtt_get_subscriptions(connection_id: str):
    """获取订阅表"""
    subscriptions = mqtt_manager.get_subscriptions(connection_id)
    return {"success": True, "data": {"subscriptions": subscriptions}}


@router.get("/status/{connection_id}")
async def mqtt_get_status(connection_id: str):
    """获取 MQTT 连接状态；连接不存在返回 {connected: false}"""
    status = mqtt_manager.get_status(connection_id)
    if status is None:
        return {"connected": False}
    return status
