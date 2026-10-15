#!/usr/bin/env python3
"""
TCP 连接测试服务器
用于测试网络调试助手的TCP客户端功能
"""

import socket
import threading
import time

def echo_server(host='127.0.0.1', port=8080):
    """创建一个简单的回显服务器"""
    print(f"启动测试服务器: {host}:{port}")
    
    server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    
    try:
        server_socket.bind((host, port))
        server_socket.listen(5)
        print(f"服务器监听中...")
        
        while True:
            try:
                client_socket, address = server_socket.accept()
                print(f"新客户端连接: {address}")
                
                # 创建线程处理客户端
                client_thread = threading.Thread(
                    target=handle_client,
                    args=(client_socket, address)
                )
                client_thread.daemon = True
                client_thread.start()
                
            except KeyboardInterrupt:
                print("\n停止服务器...")
                break
            except Exception as e:
                print(f"接受连接时出错: {e}")
                
    except Exception as e:
        print(f"服务器启动失败: {e}")
    finally:
        server_socket.close()

def handle_client(client_socket, address):
    """处理客户端连接"""
    try:
        # 发送欢迎消息
        welcome_msg = f"欢迎连接到测试服务器! 时间: {time.strftime('%Y-%m-%d %H:%M:%S')}\n"
        client_socket.send(welcome_msg.encode('utf-8'))
        
        while True:
            try:
                # 接收数据
                data = client_socket.recv(1024)
                if not data:
                    break
                
                received_text = data.decode('utf-8', errors='ignore')
                print(f"从 {address} 接收到: {received_text.strip()}")
                
                # 回显数据 (添加时间戳和前缀)
                response = f"[{time.strftime('%H:%M:%S')}] 回显: {received_text}"
                client_socket.send(response.encode('utf-8'))
                
            except socket.timeout:
                continue
            except Exception as e:
                print(f"处理客户端 {address} 数据时出错: {e}")
                break
                
    except Exception as e:
        print(f"客户端 {address} 连接出错: {e}")
    finally:
        print(f"客户端 {address} 断开连接")
        client_socket.close()

if __name__ == "__main__":
    try:
        echo_server()
    except KeyboardInterrupt:
        print("\n程序结束")