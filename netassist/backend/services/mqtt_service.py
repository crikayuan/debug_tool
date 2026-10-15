"""
MQTT 连接管理服务 - 基于 paho-mqtt 2.x（CallbackAPIVersion.VERSION2）

职责：
- paho 客户端生命周期（连接 / 断开 / 自动重连）
- 订阅表维护与断线重连后无条件重放
- 接收消息队列（供 WebSocket 50ms 轮询取用）
- 收发统计

设计约定（对齐 `docs/设计-MQTT增量.md` §3.2）：
- 单连接模型：每个后端进程只维护一个 MQTT 连接（多开由多实例承载）
- connection_id 形如 `mqtt:{host}:{port}`
- userdata 统一设为 connection_id，回调据此定位连接
- 一期固定 MQTT 3.1.1，不含 TLS / 遗嘱 / 5.0 / WebSocket 传输
"""

import time
import uuid
import threading
import collections
from typing import Dict, List, Optional, Tuple

import paho.mqtt.client as mqtt

from config import settings
from models import MqttConfig, ConnectionStats, APIResponse


class MqttConnectionManager:
    """MQTT 连接管理器 - 单连接模型，支持订阅表重放与消息队列"""

    def __init__(self) -> None:
        """初始化连接表"""
        self.connections: Dict[str, dict] = {}

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _gen_client_id(self) -> str:
        """生成 debug-assistant-<8位随机十六进制>"""
        return f"{settings.MQTT_CLIENT_ID_PREFIX}{uuid.uuid4().hex[:8]}"

    @staticmethod
    def _build_client_id(raw_client_id: str, with_time: bool) -> str:
        """
        生成/规整实际使用的 ClientID。

        Args:
            raw_client_id: 用户填写的 ClientID（可为空）
            with_time: 为 True 时追加 -<epoch秒>，规避多开撞名
        """
        base = (raw_client_id or "").strip()
        if not base:
            base = f"{settings.MQTT_CLIENT_ID_PREFIX}{uuid.uuid4().hex[:8]}"
        if with_time:
            base = f"{base}-{int(time.time())}"
        return base

    @staticmethod
    def _rc_value(reason_code) -> int:
        """
        兼容提取 reason_code 的整数值。

        paho VERSION2 的 on_connect/on_subscribe 回调传入的是 `ReasonCode` 对象
        （非 int 子类），需通过 `.value` 取整；同时兼容直接传 int 的情况。
        """
        if reason_code is None:
            return 0
        if isinstance(reason_code, int) and not isinstance(reason_code, bool):
            return int(reason_code)
        value = getattr(reason_code, "value", None)
        if isinstance(value, int):
            return value
        try:
            return int(reason_code)
        except Exception:
            return 0

    @staticmethod
    def _map_reason_code(reason_code: int) -> str:
        """将 CONNACK 非 0 reason_code 映射为人类可读文案"""
        mapping = {
            1: "连接被拒绝：不支持的协议版本",
            2: "连接被拒绝：ClientID 不合法",
            3: "连接被拒绝：服务器不可用",
            4: "连接被拒绝：用户名或密码错误",
            5: "ClientID 被占用，请更换",
            128: "连接被拒绝：未指定错误",
            134: "连接被拒绝：认证失败",
            135: "连接被拒绝：未授权",
        }
        return mapping.get(reason_code, f"连接被拒绝（原因码 {reason_code}）")

    @staticmethod
    def match_topic(actual: str, pattern: str) -> bool:
        """
        MQTT 主题通配符匹配。

        - `+` 匹配单层
        - `#` 匹配剩余全部层级（含 0 层，须位于末尾）
        """
        a_levels = actual.split("/") if actual else []
        p_levels = pattern.split("/") if pattern else []
        for idx, seg in enumerate(p_levels):
            if seg == "#":
                # `#` 匹配当前及其后所有层级（包括本层为空）
                return True
            if idx >= len(a_levels):
                return False
            if seg == "+":
                continue
            if seg != a_levels[idx]:
                return False
        return len(a_levels) == len(p_levels)

    # ------------------------------------------------------------------
    # 连接生命周期
    # ------------------------------------------------------------------
    def connect(self, config: MqttConfig) -> APIResponse:
        """
        建立 MQTT 连接（同步建链 + 等待 CONNACK，最长 MQTT_CONNECT_TIMEOUT 秒）。

        Returns:
            APIResponse，成功时 data={connection_id, client_id}
        """
        host = (config.host or "").strip()
        if not host:
            return APIResponse(success=False, message="Broker 地址不能为空")

        if config.port < 1 or config.port > 65535:
            return APIResponse(
                success=False,
                message=f"端口号必须在1-65535范围内，当前值: {config.port}",
            )

        connection_id = f"mqtt:{host}:{config.port}"

        # 同名连接已存在时先断开，避免端口/资源泄漏
        if connection_id in self.connections:
            try:
                self.disconnect(connection_id)
            except Exception:
                self.connections.pop(connection_id, None)

        client_id = self._build_client_id(
            config.client_id, bool(config.client_id_with_time)
        )

        connack_event = threading.Event()
        try:
            client = mqtt.Client(
                callback_api_version=mqtt.CallbackAPIVersion.VERSION2,
                client_id=client_id,
                clean_session=bool(config.clean),
                protocol=mqtt.MQTTv311,
                reconnect_on_failure=bool(config.reconnect),
            )
        except Exception as e:
            return APIResponse(success=False, message=f"创建 MQTT 客户端失败: {str(e)}")

        # 回调注册（VERSION2 签名，详见模块 docstring 与设计文档 §3.2）
        client.on_connect = self._on_connect
        client.on_disconnect = self._on_disconnect
        client.on_message = self._on_message
        client.on_subscribe = self._on_subscribe
        client.on_publish = self._on_publish

        # userdata 设为 connection_id，回调据此定位连接
        client.user_data_set(connection_id)

        # 用户名/密码（有则设置）
        if config.username:
            try:
                client.username_pw_set(config.username, config.password or None)
            except Exception as e:
                return APIResponse(success=False, message=f"设置用户名/密码失败: {str(e)}")

        # 重连参数（ms → s）
        reconnect_period = config.reconnect_period or settings.MQTT_RECONNECT_PERIOD
        try:
            client.reconnect_delay_set(
                min_delay=max(1, int(reconnect_period) // 1000),
                max_delay=max(1, int(reconnect_period) // 1000 * 12),
            )
        except Exception:
            # 重连参数为非致命项，忽略
            pass

        # 先登记连接状态，再启动 loop（回调可能立即触发）
        conn = {
            "client": client,
            "config": config.model_dump(),
            "connected": False,
            "connack_event": connack_event,
            "connect_error": None,
            "manual_disconnect": False,
            "stats": ConnectionStats().model_dump(),
            "queue": collections.deque(maxlen=settings.MQTT_QUEUE_MAXLEN),
            "subscriptions": {},
            "sub_mids": {},
            "connection_id": connection_id,
            "client_id": client_id,
        }
        self.connections[connection_id] = conn

        # 同步建链（失败即抛）
        try:
            client.connect(host, config.port, config.keepalive)
        except Exception as e:
            self.connections.pop(connection_id, None)
            return APIResponse(success=False, message=f"连接失败: {str(e)}")

        # 启动网络循环线程
        try:
            client.loop_start()
        except Exception as e:
            self.connections.pop(connection_id, None)
            return APIResponse(success=False, message=f"启动网络循环失败: {str(e)}")

        # 等待 CONNACK
        received = connack_event.wait(timeout=settings.MQTT_CONNECT_TIMEOUT)
        if not received:
            self._cleanup_connection(connection_id)
            return APIResponse(
                success=False,
                message=f"连接超时：{settings.MQTT_CONNECT_TIMEOUT} 秒内未收到 CONNACK",
            )

        if not conn["connected"]:
            err = conn.get("connect_error") or "连接被拒绝"
            self._cleanup_connection(connection_id)
            return APIResponse(success=False, message=err)

        return APIResponse(
            success=True,
            message=f"成功连接到 MQTT Broker: {host}:{config.port}",
            data={"connection_id": connection_id, "client_id": client_id},
            connection_id=connection_id,
        )

    def _cleanup_connection(self, connection_id: str) -> None:
        """关闭并移除连接（内部使用，吞掉所有异常）"""
        conn = self.connections.pop(connection_id, None)
        if not conn:
            return
        conn["manual_disconnect"] = True
        client = conn.get("client")
        if client is not None:
            try:
                client.disconnect()
            except Exception:
                pass
            try:
                client.loop_stop()
            except Exception:
                pass

    def disconnect(self, connection_id: str) -> APIResponse:
        """主动断开连接并清理资源；订阅表随连接销毁（持久化由前端负责）"""
        if connection_id not in self.connections:
            return APIResponse(success=False, message="连接不存在")

        try:
            self._cleanup_connection(connection_id)
            return APIResponse(success=True, message="连接已断开")
        except Exception as e:
            return APIResponse(success=False, message=f"断开连接失败: {str(e)}")

    # ------------------------------------------------------------------
    # 发布 / 订阅
    # ------------------------------------------------------------------
    def publish(
        self,
        connection_id: str,
        topic: str,
        payload: bytes,
        qos: int,
        retain: bool,
    ) -> APIResponse:
        """
        发布消息。仅入队成功即返回，不阻塞等待 ACK。

        Returns:
            APIResponse，成功时 data={mid}
        """
        conn = self.connections.get(connection_id)
        if conn is None:
            return APIResponse(success=False, message="连接不存在")

        if not conn.get("connected"):
            return APIResponse(success=False, message="连接未建立或已断开")

        if not topic or not topic.strip():
            return APIResponse(success=False, message="发布主题不能为空")

        try:
            info = conn["client"].publish(topic, payload, qos, retain)
            if info is None:
                conn["stats"]["error_count"] += 1
                return APIResponse(success=False, message="发布失败：客户端未返回结果")

            if info.rc != mqtt.MQTT_ERR_SUCCESS:
                conn["stats"]["error_count"] += 1
                return APIResponse(success=False, message=f"发布失败（错误码 {info.rc}）")

            conn["stats"]["send_bytes"] += len(payload)
            conn["stats"]["send_count"] += 1
            return APIResponse(
                success=True, message="发布成功", data={"mid": info.mid}
            )
        except Exception as e:
            conn["stats"]["error_count"] += 1
            return APIResponse(success=False, message=f"发布失败: {str(e)}")

    def subscribe(self, connection_id: str, topic: str, qos: int) -> APIResponse:
        """订阅主题：写入订阅表（state=pending）→ client.subscribe → on_subscribe 更新状态"""
        conn = self.connections.get(connection_id)
        if conn is None:
            return APIResponse(success=False, message="连接不存在")

        if not topic or not topic.strip():
            return APIResponse(success=False, message="订阅主题不能为空")

        topic = topic.strip()
        existing = conn["subscriptions"].get(topic)
        conn["subscriptions"][topic] = {
            "qos": qos,
            "state": "pending",
            "count": existing.get("count", 0) if existing else 0,
        }

        try:
            result, mid = conn["client"].subscribe(topic, qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                conn["subscriptions"][topic]["state"] = "failed"
                conn["stats"]["error_count"] += 1
                return APIResponse(success=False, message=f"订阅失败（错误码 {result}）")

            if mid is not None:
                conn.setdefault("sub_mids", {})[mid] = topic

            return APIResponse(
                success=True,
                message=f"已订阅: {topic}",
                data={"topic": topic, "qos": qos},
            )
        except Exception as e:
            conn["subscriptions"][topic]["state"] = "failed"
            conn["stats"]["error_count"] += 1
            return APIResponse(success=False, message=f"订阅失败: {str(e)}")

    def unsubscribe(self, connection_id: str, topic: str) -> APIResponse:
        """取消订阅并从订阅表移除"""
        conn = self.connections.get(connection_id)
        if conn is None:
            return APIResponse(success=False, message="连接不存在")

        try:
            result, _mid = conn["client"].unsubscribe(topic)
            conn["subscriptions"].pop(topic, None)
            if result != mqtt.MQTT_ERR_SUCCESS:
                return APIResponse(success=False, message=f"取消订阅失败（错误码 {result}）")
            return APIResponse(success=True, message=f"已取消订阅: {topic}")
        except Exception as e:
            return APIResponse(success=False, message=f"取消订阅失败: {str(e)}")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------
    def get_subscriptions(self, connection_id: str) -> List[dict]:
        """返回 [{topic, qos, state, count}]（count 为该订阅命中的消息数）"""
        conn = self.connections.get(connection_id)
        if conn is None:
            return []
        return [
            {
                "topic": topic,
                "qos": info.get("qos", 0),
                "state": info.get("state", "pending"),
                "count": info.get("count", 0),
            }
            for topic, info in conn.get("subscriptions", {}).items()
        ]

    def read_data(
        self, connection_id: str
    ) -> Optional[Tuple[str, bytes, int, bool]]:
        """从队列取一条：(topic, payload_bytes, qos, retain)；无数据返回 None（供 WS 轮询）"""
        conn = self.connections.get(connection_id)
        if conn is None:
            return None
        queue = conn.get("queue")
        if not queue:
            return None
        try:
            return queue.popleft()
        except Exception:
            return None

    def get_status(self, connection_id: str) -> Optional[dict]:
        """返回连接状态 dict；连接不存在返回 None"""
        conn = self.connections.get(connection_id)
        if conn is None:
            return None
        return {
            "connected": conn.get("connected", False),
            "host": conn["config"].get("host", ""),
            "port": conn["config"].get("port", 0),
            "client_id": conn.get("client_id", ""),
            "stats": conn.get("stats", {}),
            "subscriptions": self.get_subscriptions(connection_id),
            "error": conn.get("connect_error"),
        }

    def get_connection(self, connection_id: str) -> Optional[dict]:
        """返回连接内部 dict（供 WS 端点判断存在性与心跳取值）"""
        return self.connections.get(connection_id)

    # ------------------------------------------------------------------
    # paho 回调（CallbackAPIVersion.VERSION2）
    # ------------------------------------------------------------------
    def _on_connect(self, client, userdata, flags, reason_code, properties=None):
        """连接/CONNACK 回调：成功则重放订阅表，失败则记录原因"""
        conn = self.get_connection(userdata)
        if conn is None:
            return

        try:
            rc = self._rc_value(reason_code)
        except Exception:
            rc = -1

        if rc == 0:
            conn["connected"] = True
            conn["connect_error"] = None
            conn["manual_disconnect"] = False
            # 无条件重放订阅表（含自动重连场景）
            for topic, info in list(conn.get("subscriptions", {}).items()):
                try:
                    result, mid = client.subscribe(topic, info.get("qos", 0))
                    if result == mqtt.MQTT_ERR_SUCCESS and mid is not None:
                        conn.setdefault("sub_mids", {})[mid] = topic
                except Exception:
                    pass
            conn["connack_event"].set()
        else:
            conn["connected"] = False
            conn["connect_error"] = self._map_reason_code(rc)
            conn["stats"]["error_count"] += 1
            conn["connack_event"].set()

    def _on_disconnect(self, client, userdata, flags, reason_code, properties=None):
        """断开回调：manual_disconnect 为 False 视为异常掉线"""
        conn = self.get_connection(userdata)
        if conn is None:
            return
        conn["connected"] = False
        if not conn.get("manual_disconnect"):
            try:
                rc = self._rc_value(reason_code)
            except Exception:
                rc = 0
            if rc != 0:
                conn["stats"]["error_count"] += 1

    def _on_message(self, client, userdata, msg):
        """消息回调：dict 保留原始 bytes 入队，累加统计与订阅命中计数"""
        conn = self.get_connection(userdata)
        if conn is None:
            return

        try:
            payload = bytes(msg.payload)
        except Exception:
            payload = b""

        topic = msg.topic
        qos = getattr(msg, "qos", 0)
        retain = bool(getattr(msg, "retain", False))

        conn["queue"].append((topic, payload, qos, retain))
        conn["stats"]["receive_bytes"] += len(payload)
        conn["stats"]["receive_count"] += 1

        # 匹配订阅表，命中计数累加
        for sub_topic, info in conn.get("subscriptions", {}).items():
            if self.match_topic(topic, sub_topic):
                info["count"] = info.get("count", 0) + 1

    def _on_subscribe(self, client, userdata, mid, reason_codes, properties=None):
        """订阅确认回调：reason_codes >= 128 视为失败"""
        conn = self.get_connection(userdata)
        if conn is None:
            return

        topic = conn.get("sub_mids", {}).pop(mid, None)
        if topic is None:
            return

        info = conn.get("subscriptions", {}).get(topic)
        if info is None:
            return

        ok = True
        try:
            for rc in reason_codes:
                if self._rc_value(rc) >= 128:
                    ok = False
                    break
        except Exception:
            ok = True

        info["state"] = "subscribed" if ok else "failed"

    def _on_publish(self, client, userdata, mid, reason_codes, properties=None):
        """发布确认回调（QoS1/2 送达确认，仅记录，不阻塞发送返回）"""
        conn = self.get_connection(userdata)
        if conn is None:
            return
        # 仅记录最近一次被确认的 mid，不改动发送统计（发送统计在 publish() 即时累加）
        conn["last_pub_mid"] = mid


# 实例化 MQTT 连接管理器
mqtt_manager = MqttConnectionManager()
