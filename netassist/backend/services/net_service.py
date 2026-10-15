"""
网络连接管理服务 - 支持TCP和UDP
支持 TCP Server 多客户端管理（客户端列表 / 广播 / 定向发送）
"""

import socket
import select
from typing import Dict, List, Optional, Tuple

from models import NetConfig, ConnectionStats, APIResponse


class NetConnectionManager:
    """网络连接管理器 - 支持TCP和UDP"""

    def __init__(self):
        self.connections: Dict[str, dict] = {}
        self._client_seq = 0

    def _next_client_id(self) -> str:
        self._client_seq += 1
        return str(self._client_seq)

    def create_connection(self, config: NetConfig) -> APIResponse:
        """创建网络连接"""
        if config.protocol not in ["tcp", "udp"]:
            return APIResponse(
                success=False, message=f"不支持的协议类型: {config.protocol}"
            )

        if config.port < 1 or config.port > 65535:
            return APIResponse(
                success=False,
                message=f"端口号必须在1-65535范围内，当前值: {config.port}",
            )

        connection_id = f"{config.protocol}:{config.host}:{config.port}"

        try:
            if config.protocol == "tcp":
                sock = self._create_tcp_connection(config)
            else:
                sock = self._create_udp_connection(config)

            self.connections[connection_id] = {
                "socket": sock,
                "config": config.dict(),
                "connected": True,
                "stats": ConnectionStats().dict(),
                "clients": (
                    {} if config.mode == "server" and config.protocol == "tcp" else None
                ),
                "remote_address": (
                    None if config.mode == "server" else (config.host, config.port)
                ),
            }

            message = (
                f"成功创建{config.protocol.upper()}连接: {config.host}:{config.port}"
                if config.mode == "client"
                else f"{config.protocol.upper()}服务器已启动，监听 {config.host}:{config.port}"
            )

            return APIResponse(
                success=True,
                message=message,
                data={"connection_id": connection_id},
                connection_id=connection_id,
            )

        except Exception as e:
            return APIResponse(success=False, message=f"创建连接失败: {str(e)}")

    def _create_tcp_connection(self, config: NetConfig) -> socket.socket:
        """创建TCP连接"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if config.mode == "client":
            sock.settimeout(3.0)
            sock.connect((config.host, config.port))
            sock.settimeout(0.1)
        else:
            sock.bind((config.host, config.port))
            sock.listen(128)
            sock.settimeout(0.1)

        return sock

    def _create_udp_connection(self, config: NetConfig) -> socket.socket:
        """创建UDP连接"""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)

        if config.mode == "server":
            sock.bind((config.host, config.port))

        sock.settimeout(0.1)
        return sock

    def disconnect(self, connection_id: str) -> APIResponse:
        """断开网络连接"""
        if connection_id not in self.connections:
            return APIResponse(success=False, message="连接不存在")

        try:
            conn = self.connections[connection_id]

            if conn.get("clients"):
                for client in conn["clients"].values():
                    try:
                        client["sock"].close()
                    except Exception:
                        pass

            conn["socket"].close()
            del self.connections[connection_id]

            return APIResponse(success=True, message="连接已断开")

        except Exception as e:
            return APIResponse(success=False, message=f"断开连接失败: {str(e)}")

    def get_clients(self, connection_id: str) -> List[dict]:
        """获取 TCP Server 已连接客户端列表"""
        conn = self.connections.get(connection_id)
        if not conn or not conn.get("clients"):
            return []
        return [
            {"id": cid, "address": c["addr"]}
            for cid, c in conn["clients"].items()
        ]

    def disconnect_client(self, connection_id: str, client_id: str) -> APIResponse:
        """断开 TCP Server 的单个客户端"""
        if connection_id not in self.connections:
            return APIResponse(success=False, message="连接不存在")

        conn = self.connections[connection_id]
        clients = conn.get("clients")
        if not clients or client_id not in clients:
            return APIResponse(success=False, message="客户端不存在")

        client = clients.pop(client_id)
        try:
            client["sock"].close()
        except Exception:
            pass

        return APIResponse(success=True, message=f"已断开客户端 {client['addr']}")

    def send_data(
        self, connection_id: str, data: bytes, target: Optional[str] = None
    ) -> APIResponse:
        """
        发送网络数据。

        Args:
            connection_id: 连接ID
            data: 要发送的数据
            target: 定向发送目标；None/"all" 广播，逗号分隔 client_id 定向发送
        """
        if connection_id not in self.connections:
            return APIResponse(success=False, message="连接不存在")

        try:
            conn = self.connections[connection_id]
            sock = conn["socket"]

            if conn["config"]["protocol"] == "tcp":
                if conn["config"]["mode"] == "client":
                    try:
                        sock.send(data)
                    except BrokenPipeError:
                        conn["connected"] = False
                        return APIResponse(success=False, message="连接已断开")
                    except ConnectionResetError:
                        conn["connected"] = False
                        return APIResponse(success=False, message="连接被重置")
                else:
                    # TCP 服务器模式：广播或定向
                    clients = conn.get("clients", {})
                    if not clients:
                        return APIResponse(success=False, message="没有连接的客户端")

                    target_ids = None
                    if target and target != "all":
                        target_ids = set(target.split(","))

                    targets = []
                    if target_ids:
                        targets = [
                            (cid, c) for cid, c in clients.items() if cid in target_ids
                        ]
                    else:
                        targets = list(clients.items())

                    if not targets:
                        return APIResponse(success=False, message="没有可发送的目标客户端")

                    success_clients = 0
                    for cid, c in targets:
                        try:
                            c["sock"].send(data)
                            success_clients += 1
                        except Exception:
                            try:
                                c["sock"].close()
                            except Exception:
                                pass
                            clients.pop(cid, None)

                    if success_clients == 0:
                        return APIResponse(success=False, message="所有目标客户端已断开")

                    if target_ids:
                        return APIResponse(
                            success=True, message=f"已发送给 {success_clients} 个客户端"
                        )
            else:
                # UDP模式
                if conn.get("remote_address"):
                    try:
                        sock.sendto(data, conn["remote_address"])
                    except Exception as e:
                        return APIResponse(success=False, message=f"UDP发送失败: {str(e)}")
                else:
                    return APIResponse(
                        success=False, message="UDP服务器模式下请先设置远程地址"
                    )

            conn["stats"]["send_count"] += 1
            conn["stats"]["send_bytes"] += len(data)

            return APIResponse(success=True, message="数据发送成功")

        except Exception as e:
            print(f"发送数据异常: {str(e)}")
            if connection_id in self.connections:
                self.connections[connection_id]["stats"]["error_count"] += 1
            return APIResponse(success=False, message=f"发送失败: {str(e)}")

    def read_data(
        self, connection_id: str
    ) -> Optional[Tuple[Optional[str], bytes]]:
        """
        读取网络数据。

        Returns:
            (client_id, data) 元组；TCP Server 模式 client_id 为来源客户端，
            其余模式 client_id 为 None；无数据返回 None。
        """
        if connection_id not in self.connections:
            return None

        try:
            conn = self.connections[connection_id]
            sock = conn["socket"]

            if conn["config"]["protocol"] == "tcp":
                if conn["config"]["mode"] == "client":
                    try:
                        readable, _, exceptional = select.select(
                            [sock], [], [sock], 0.01
                        )
                        if sock in exceptional:
                            conn["connected"] = False
                            return None

                        if sock in readable:
                            data = sock.recv(4096)
                            if data:
                                conn["stats"]["receive_bytes"] += len(data)
                                conn["stats"]["receive_count"] += 1
                                return (None, data)
                            else:
                                conn["connected"] = False
                                return None
                    except socket.timeout:
                        pass
                    except Exception as e:
                        print(f"TCP客户端读取数据异常: {str(e)}")
                        conn["stats"]["error_count"] += 1
                        conn["connected"] = False
                        return None
                else:
                    # TCP 服务器模式：处理多客户端
                    try:
                        sockets_to_watch = [sock]
                        clients = conn.get("clients", {})
                        if clients:
                            sockets_to_watch.extend([c["sock"] for c in clients.values()])

                        readable, _, exceptional = select.select(
                            sockets_to_watch, [], sockets_to_watch, 0.01
                        )

                        for s in exceptional:
                            if s == sock:
                                conn["connected"] = False
                                return None
                            else:
                                self._remove_client_by_sock(conn, s)

                        for s in readable:
                            if s == sock:
                                # 新连接
                                try:
                                    client_sock, addr = s.accept()
                                    client_sock.settimeout(0.1)
                                    cid = self._next_client_id()
                                    conn["clients"][cid] = {
                                        "sock": client_sock,
                                        "addr": f"{addr[0]}:{addr[1]}",
                                    }
                                    print(f"新客户端连接: {addr} (id={cid})")
                                except Exception:
                                    pass
                            else:
                                # 从客户端接收数据
                                client_id = self._find_client_id(conn, s)
                                try:
                                    data = s.recv(4096)
                                    if data:
                                        conn["stats"]["receive_bytes"] += len(data)
                                        conn["stats"]["receive_count"] += 1
                                        return (client_id, data)
                                    else:
                                        self._remove_client_by_sock(conn, s)
                                except Exception:
                                    self._remove_client_by_sock(conn, s)
                    except Exception as e:
                        print(f"TCP服务器读取数据异常: {str(e)}")
                        conn["stats"]["error_count"] += 1
                        return None
            else:
                # UDP模式
                try:
                    readable, _, exceptional = select.select(
                        [sock], [], [sock], 0.01
                    )
                    if sock in exceptional:
                        conn["connected"] = False
                        return None

                    if sock in readable:
                        data, addr = sock.recvfrom(4096)
                        if data:
                            conn["stats"]["receive_bytes"] += len(data)
                            conn["stats"]["receive_count"] += 1
                            if conn["config"]["mode"] == "server":
                                conn["remote_address"] = addr
                            return (None, data)
                except socket.timeout:
                    pass
                except Exception as e:
                    print(f"UDP读取数据异常: {str(e)}")
                    conn["stats"]["error_count"] += 1
                    return None

        except Exception as e:
            if connection_id in self.connections:
                self.connections[connection_id]["stats"]["error_count"] += 1
                print(f"读取数据异常: {str(e)}")

        return None

    def _find_client_id(self, conn: dict, sock: socket.socket) -> Optional[str]:
        for cid, c in conn.get("clients", {}).items():
            if c["sock"] is sock:
                return cid
        return None

    def _remove_client_by_sock(self, conn: dict, sock: socket.socket):
        cid = self._find_client_id(conn, sock)
        if cid:
            conn["clients"].pop(cid, None)
        try:
            sock.close()
        except Exception:
            pass

    def get_connection_status(self, connection_id: str) -> Optional[Dict]:
        """获取连接状态"""
        if connection_id in self.connections:
            conn = self.connections[connection_id]
            status = {
                "connected": conn["connected"],
                "protocol": conn["config"].get("protocol", "tcp"),
                "mode": conn["config"].get("mode", "client"),
                "host": conn["config"].get("host", ""),
                "port": conn["config"].get("port", 0),
                "stats": conn["stats"],
            }

            if conn.get("clients"):
                status["clients"] = len(conn["clients"])

            if conn.get("remote_address"):
                status["remote_address"] = conn["remote_address"]

            return status
        return None

    def get_connection(self, connection_id: str) -> Optional[Dict]:
        """获取连接信息"""
        return self.connections.get(connection_id)


# 实例化网络连接管理器
net_manager = NetConnectionManager()
