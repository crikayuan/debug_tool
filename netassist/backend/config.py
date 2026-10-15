"""
配置文件
"""

import os
import json
from typing import List
from pathlib import Path


class Settings:
    """应用配置"""

    APP_NAME: str = "调试助手"
    VERSION: str = "1.3.1"
    HOST: str = "0.0.0.0"
    PORT: int = 20001  # 默认端口改为20001

    # CORS配置
    CORS_ORIGINS: List[str] = ["*"]  # 在生产环境中应该设置具体的域名
    CORS_ALLOW_CREDENTIALS: bool = True
    CORS_ALLOW_METHODS: List[str] = ["*"]
    CORS_ALLOW_HEADERS: List[str] = ["*"]

    # WebSocket配置
    WEBSOCKET_PING_INTERVAL: float = 0.1
    WEBSOCKET_TIMEOUT: int = 60

    # 静态文件配置
    STATIC_DIR: str = "static"

    # MQTT 默认配置
    MQTT_DEFAULT_HOST: str = "broker.emqx.io"  # 默认 Broker 地址
    MQTT_DEFAULT_PORT: int = 1883  # 默认端口（一期明文 1883）
    MQTT_DEFAULT_KEEPALIVE: int = 60  # 心跳（秒）
    MQTT_CONNECT_TIMEOUT: int = 10  # 等待 CONNACK 的超时（秒）
    MQTT_RECONNECT_PERIOD: int = 4000  # 自动重连周期（毫秒）
    MQTT_QUEUE_MAXLEN: int = 5000  # 接收队列上限
    MQTT_CLIENT_ID_PREFIX: str = "debug-assistant-"  # 自动 ClientID 前缀

    # HTTP Server 模块（第五模式）默认配置
    HTTP_DEFAULT_PORT: int = 8080  # 默认监听端口
    HTTP_DEFAULT_BIND: str = "0.0.0.0"  # 默认绑定地址（局域网可访问）
    HTTP_MAX_RECORDS: int = 2000  # 内存中保留的请求记录上限
    HTTP_MAX_BODY: int = 10 * 1024 * 1024  # 单请求体读取上限（10MB）
    HTTP_RESERVED_PORT_START: int = 20001  # 本程序自用端口段起点（禁止作为监听端口）
    HTTP_RESERVED_PORT_END: int = 20050  # 本程序自用端口段终点

    # 配置文件路径
    CONFIG_FILE: str = "/etc/net-debug-tools/config.json"

    def __init__(self):
        """初始化配置，从配置文件加载，环境变量优先"""
        self.load_config()
        # 环境变量优先（云部署注入 PORT / HOST）
        if os.environ.get("PORT"):
            try:
                self.PORT = int(os.environ["PORT"])
            except ValueError:
                pass
        if os.environ.get("HOST"):
            self.HOST = os.environ["HOST"]

    def load_config(self):
        """从配置文件加载配置"""
        try:
            if os.path.exists(self.CONFIG_FILE):
                with open(self.CONFIG_FILE, "r", encoding="utf-8") as f:
                    config_data = json.load(f)
                    self.PORT = config_data.get("port", self.PORT)
                    self.HOST = config_data.get("host", self.HOST)
        except Exception as e:
            print(f"警告：加载配置文件失败: {e}，使用默认配置")

    def save_config(self):
        """保存配置到文件"""
        try:
            # 确保配置目录存在
            config_dir = os.path.dirname(self.CONFIG_FILE)
            os.makedirs(config_dir, exist_ok=True)

            config_data = {"port": self.PORT, "host": self.HOST}

            with open(self.CONFIG_FILE, "w", encoding="utf-8") as f:
                json.dump(config_data, f, indent=2, ensure_ascii=False)

            return True
        except Exception as e:
            print(f"保存配置文件失败: {e}")
            return False

    def update_port(self, new_port: int) -> bool:
        """更新端口配置"""
        if 1 <= new_port <= 65535:
            self.PORT = new_port
            return self.save_config()
        return False


settings = Settings()
