"""
串口连接管理服务
"""

import serial
import serial.tools.list_ports
from typing import Dict, List, Optional
from models import SerialConfig, SerialPort, ConnectionStats, APIResponse


class SerialConnectionManager:
    """串口连接管理器"""

    def __init__(self):
        self.connections: Dict[str, dict] = {}

    def get_available_ports(self) -> APIResponse:
        """
        获取可用串口列表，包括虚拟串口

        Returns:
            APIResponse: 包含串口列表的响应
        """
        try:
            # 使用pyserial获取标准串口列表
            ports = serial.tools.list_ports.comports()
            port_list = [
                SerialPort(device=port.device, description=port.description).dict()
                for port in ports
            ]

            # 创建一个已存在端口的集合，避免重复
            existing_ports = {port["device"] for port in port_list}

            # 手动检查常见的虚拟串口路径
            import os
            import glob

            # 检查/dev/ttyV*虚拟串口
            for port_path in glob.glob("/dev/tty*"):
                if port_path not in existing_ports and os.path.exists(port_path):
                    try:
                        # 尝试获取链接信息
                        if os.path.islink(port_path):
                            target = os.readlink(port_path)
                            description = f"Virtual Serial Port (links to {target})"
                        else:
                            description = "Virtual Serial Port"

                        port_list.append(
                            {"device": port_path, "description": description}
                        )
                        existing_ports.add(port_path)
                    except Exception:
                        # 如果无法获取详细信息，至少添加端口名
                        port_list.append(
                            {"device": port_path, "description": "Virtual Serial Port"}
                        )
                        existing_ports.add(port_path)

            # 检查/dev/pts设备（伪终端，常用于虚拟串口）
            for port_path in glob.glob("/dev/pts/[0-9]*"):
                # 跳过已经添加的端口
                if port_path not in existing_ports and os.path.exists(port_path):
                    # 只添加那些没有被链接到的pts设备（避免重复）
                    is_linked = False
                    for link_path in glob.glob("/dev/ttyV*"):
                        try:
                            if os.path.islink(link_path) and os.readlink(
                                link_path
                            ) == os.path.basename(port_path):
                                is_linked = True
                                break
                        except Exception:
                            pass

                    if not is_linked:
                        try:
                            # 检查是否可以打开（简单的可访问性测试）
                            with open(port_path, "rb") as f:
                                # 只是测试打开权限，不读写
                                pass
                            port_list.append(
                                {"device": port_path, "description": "Pseudo Terminal"}
                            )
                        except Exception:
                            # 如果无法打开，可能不是可用的串口
                            pass

            return APIResponse(
                success=True, message="获取串口列表成功", data={"ports": port_list}
            )
        except Exception as e:
            return APIResponse(
                success=False, message=f"获取串口列表失败: {str(e)}", data={"ports": []}
            )

    def create_connection(self, config: SerialConfig) -> APIResponse:
        """
        创建串口连接

        Args:
            config: 串口配置

        Returns:
            APIResponse: 连接结果
        """
        try:
            # 停止位映射
            stop_bits_map = {
                1: serial.STOPBITS_ONE,
                1.5: serial.STOPBITS_ONE_POINT_FIVE,
                2: serial.STOPBITS_TWO,
            }

            # 校验位映射
            parity_map = {
                "none": serial.PARITY_NONE,
                "odd": serial.PARITY_ODD,
                "even": serial.PARITY_EVEN,
                "mark": serial.PARITY_MARK,
                "space": serial.PARITY_SPACE,
            }

            ser = serial.Serial(
                port=config.port,
                baudrate=config.baud_rate,
                bytesize=config.data_bits,
                parity=parity_map.get(config.parity, serial.PARITY_NONE),
                stopbits=stop_bits_map.get(config.stop_bits, serial.STOPBITS_ONE),
                timeout=0.1,
                rtscts=(config.flow_control == "hardware"),
                xonxoff=(config.flow_control == "software"),
            )

            # DTR / RTS 控制信号
            try:
                ser.dtr = bool(getattr(config, "dtr", False))
                ser.rts = bool(getattr(config, "rts", False))
            except Exception:
                pass

            self.connections[config.port] = {
                "serial": ser,
                "config": config.dict(),
                "connected": True,
                "stats": ConnectionStats().dict(),
            }

            return APIResponse(success=True, message=f"串口 {config.port} 已打开")

        except Exception as e:
            return APIResponse(success=False, message=f"打开串口失败: {str(e)}")

    def disconnect(self, port: str) -> APIResponse:
        """
        断开串口连接

        Args:
            port: 串口名称

        Returns:
            APIResponse: 断开结果
        """
        if port not in self.connections:
            return APIResponse(success=False, message="串口连接不存在")

        try:
            self.connections[port]["serial"].close()
            del self.connections[port]

            return APIResponse(success=True, message="串口已关闭")

        except Exception as e:
            return APIResponse(success=False, message=f"关闭串口失败: {str(e)}")

    def send_data(self, port: str, data: bytes) -> APIResponse:
        """
        发送串口数据

        Args:
            port: 串口名称
            data: 要发送的数据

        Returns:
            APIResponse: 发送结果
        """
        if port not in self.connections:
            return APIResponse(success=False, message="串口连接不存在")

        try:
            conn = self.connections[port]
            bytes_written = conn["serial"].write(data)

            # 更新统计信息
            conn["stats"]["send_count"] += 1
            conn["stats"]["send_bytes"] += bytes_written

            return APIResponse(success=True, message="数据发送成功")

        except Exception as e:
            # 更新错误统计
            if port in self.connections:
                self.connections[port]["stats"]["error_count"] += 1

            return APIResponse(success=False, message=f"发送失败: {str(e)}")

    def read_data(self, port: str) -> Optional[bytes]:
        """
        读取串口数据

        Args:
            port: 串口名称

        Returns:
            读取到的数据或None
        """
        if port not in self.connections:
            return None

        try:
            conn = self.connections[port]
            ser = conn["serial"]

            if ser.in_waiting > 0:
                data = ser.read(ser.in_waiting)

                # 更新统计信息
                conn["stats"]["receive_bytes"] += len(data)
                conn["stats"]["receive_count"] += 1

                return data

        except Exception:
            # 更新错误统计
            if port in self.connections:
                self.connections[port]["stats"]["error_count"] += 1

        return None

    def get_connection_status(self, port: str) -> Optional[dict]:
        """
        获取串口连接状态

        Args:
            port: 串口名称

        Returns:
            连接状态信息或None
        """
        if port in self.connections:
            conn = self.connections[port]
            return {
                "connected": conn["connected"],
                "config": conn["config"],
                "stats": conn["stats"],
            }
        return None

    def get_connection(self, port: str) -> Optional[dict]:
        """获取连接对象"""
        return self.connections.get(port)


# 全局串口连接管理器实例
serial_manager = SerialConnectionManager()
