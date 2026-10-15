"""
数据模型定义
"""

from typing import List, Optional

from pydantic import BaseModel


class NetConfig(BaseModel):
    """网络连接配置"""

    mode: str  # client 或 server
    protocol: str  # tcp 或 udp
    host: str
    port: int


class TCPConfig(BaseModel):
    """TCP连接配置 (兼容旧版本)"""

    mode: str  # client 或 server
    protocol: str  # tcp 或 udp
    host: str
    port: int


class SerialConfig(BaseModel):
    """串口配置"""

    port: str
    baud_rate: int
    data_bits: int
    stop_bits: float
    parity: str
    flow_control: str = "none"
    dtr: bool = False
    rts: bool = False


class SendDataRequest(BaseModel):
    """发送数据请求"""

    data: str
    format: str = "text"  # text 或 hex
    encoding: str = "utf-8"  # utf-8 或 gbk
    end_chars: str = ""  # 结束符: "" / "\r" / "\n" / "\r\n"
    target: Optional[str] = None  # 定向发送: None=默认, "all"=广播, 逗号分隔 client_id
    append_check: Optional[str] = None  # sum / xor / lrc / crc16 / fcs

    def __init__(self, **data):
        # 确保 data 不为 None
        if data.get("data") is None:
            data["data"] = ""
        super().__init__(**data)


class ClientInfo(BaseModel):
    """TCP Server 已连接客户端信息"""

    id: str
    address: str  # "ip:port"


class CheckRequest(BaseModel):
    """校验计算请求"""

    algorithm: str  # sum / xor / lrc / crc16 / fcs
    data: str
    format: str = "hex"  # hex 或 text


class ConvertRequest(BaseModel):
    """数据转换请求"""

    data: str
    from_format: str  # hex / text
    to_format: str  # hex / text
    encoding: str = "utf-8"


class ModbusBuildRequest(BaseModel):
    """Modbus 帧拼装请求"""

    protocol: str = "rtu"  # rtu / tcp / ascii
    slave_id: int = 1
    function: int = 3  # 01/02/03/04/05/06/0F/10
    address: int = 0
    quantity: int = 1
    values: List[int] = []  # 写操作的值
    byte_order: str = "big"  # big / little / bigswap / littleswap


class LogSaveRequest(BaseModel):
    """保存日志请求"""

    filename: str
    directory: str
    scope: str = "all"  # all / rx / tx
    line_format: str = "timestamp"  # timestamp / raw / hex
    encoding: str = "utf-8"  # utf-8 / utf-8-bom / gbk
    content: str = ""  # 日志内容


class ConnectionStats(BaseModel):
    """连接统计信息"""

    send_bytes: int = 0
    receive_bytes: int = 0
    send_count: int = 0
    receive_count: int = 0
    error_count: int = 0


class NetConnectionInfo(BaseModel):
    """网络连接信息"""

    connection_id: str
    config: NetConfig
    connected: bool
    stats: ConnectionStats


class TCPConnectionInfo(BaseModel):
    """TCP连接信息 (兼容旧版本)"""

    connection_id: str
    config: TCPConfig
    connected: bool
    stats: ConnectionStats


class SerialConnectionInfo(BaseModel):
    """串口连接信息"""

    port: str
    config: SerialConfig
    connected: bool
    stats: ConnectionStats


class SerialPort(BaseModel):
    """串口设备信息"""

    device: str
    description: str


class APIResponse(BaseModel):
    """标准API响应"""

    success: bool
    message: str
    data: Optional[dict] = None
    connection_id: Optional[str] = None

    class Config:
        extra = "allow"


class PortConfigRequest(BaseModel):
    """端口配置请求"""

    port: int


class PortConfigResponse(BaseModel):
    """端口配置响应"""

    current_port: int
    host: str


class MqttConfig(BaseModel):
    """MQTT 连接配置（一期仅 3.1.1，不含 TLS/遗嘱/WS 字段）"""

    host: str = "broker.emqx.io"
    port: int = 1883
    client_id: str = ""  # 空 → 后端自动生成 debug-assistant-<8位hex>
    username: str = ""
    password: str = ""
    keepalive: int = 60  # 秒
    clean: bool = True  # Clean Session
    mqtt_version: str = "3.1.1"  # 一期固定，UI 不暴露
    reconnect: bool = True  # 自动重连
    reconnect_period: int = 4000  # ms
    client_id_with_time: bool = False  # 重连时在 ClientID 追加时间戳，规避多开冲突


class MqttPublishRequest(BaseModel):
    """MQTT 发布请求（发送格式/结束符/校验复用现有 data_utils）"""

    topic: str
    payload: str = ""
    format: str = "hex"  # text / hex（沿用现有默认 HEX）
    encoding: str = "utf-8"  # utf-8 / gbk
    qos: int = 0  # 0 / 1 / 2
    retain: bool = False
    end_chars: str = ""  # "" / "\n" / "\r\n"
    append_check: Optional[str] = None  # sum / xor / lrc / crc16 / fcs

    def __init__(self, **data):
        # 确保 payload 不为 None
        if data.get("payload") is None:
            data["payload"] = ""
        super().__init__(**data)


class MqttSubscribeRequest(BaseModel):
    """MQTT 订阅请求"""

    topic: str
    qos: int = 0  # 0 / 1 / 2


class MqttUnsubscribeRequest(BaseModel):
    """MQTT 取消订阅请求"""

    topic: str


class ScanConfig(BaseModel):
    """网络扫描配置"""

    range: str = ""  # 单表达式：192.168.1.1-254 / 192.168.1.0/24 / 单 IP
    start_ip: str = ""  # 起止写法：起始 IP
    end_ip: str = ""  # 起止写法：结束 IP
    method: str = "arp_tcp"  # 一期仅 arp_tcp（ICMP/仅ARP/TCP端口 留二期）
    concurrency: int = 128  # 并发数（8~512）
    timeout_ms: int = 500  # 单端口连接超时（毫秒）
    vendor_lookup: bool = True  # 是否查询厂商（OUI）
    resolve_hostname: bool = True  # 是否反向解析主机名
    port_scan: bool = False  # 是否执行开放端口探测（关闭时仅做存活判定）
    ports: List[int] = []  # 端口探测列表（port_scan 为 True 时生效）


class ScanResultItem(BaseModel):
    """单条扫描结果"""

    ip: str
    mac: str = ""
    vendor: str = ""
    hostname: str = ""
    delay_ms: int = 0
    ports: List[int] = []
    online: bool = True


class ScanExportItem(ScanResultItem):
    """导出用结果项（含前端维护的备注）"""

    note: str = ""


class ScanExportRequest(BaseModel):
    """导出 CSV 请求"""

    items: List[ScanExportItem] = []
    task_id: str = ""  # items 为空时可由 task_id 从服务端取全量结果
    directory: str = ""  # 目标目录；为空时使用后端当前工作目录
    filename: str = ""  # 文件名；为空时自动生成 scan_result_<时间>.csv


class HttpResponseConfig(BaseModel):
    """HTTP Server 响应配置（决定客户端收到什么）"""

    code: int = 200  # 响应状态码
    content_type: str = "application/json"  # 响应 Content-Type
    body: str = ""  # 自定义响应体（echo=False 时生效）
    delay_ms: int = 0  # 响应延迟（毫秒）
    echo: bool = True  # True=回显收到的请求体（推荐，便于对方联调）


class HttpServerConfig(BaseModel):
    """HTTP Server 启动配置"""

    port: int = 8080  # 监听端口
    bind: str = "0.0.0.0"  # 绑定地址：0.0.0.0=所有网卡 / 127.0.0.1=仅本机
    response: HttpResponseConfig = HttpResponseConfig()


class HttpExportRequest(BaseModel):
    """HTTP 请求记录导出请求"""

    directory: str = ""  # 目标目录；为空时使用后端当前工作目录
    filename: str = ""  # 文件名；为空时自动生成 http_log_<时间>.txt
