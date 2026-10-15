#!/usr/bin/env python3
"""
测试修复发送数据undefined问题的脚本
"""

import sys
import os

sys.path.append("/home/narada/net-debug-tools/backend")

from utils.data_utils import format_data_for_send
from models import SendDataRequest


def test_data_formatting():
    """测试数据格式化函数"""
    print("=== 测试数据格式化函数 ===")

    # 测试正常文本数据
    try:
        result = format_data_for_send("Hello World", "text")
        print(f"正常文本数据: 'Hello World' -> {result}")
    except Exception as e:
        print(f"正常文本数据测试失败: {e}")

    # 测试空字符串
    try:
        result = format_data_for_send("", "text")
        print(f"空字符串: '' -> {result}")
    except Exception as e:
        print(f"空字符串测试失败: {e}")

    # 测试None值
    try:
        result = format_data_for_send(None, "text")
        print(f"None值: None -> {result}")
    except Exception as e:
        print(f"None值测试失败: {e}")

    # 测试十六进制数据
    try:
        result = format_data_for_send("48656C6C6F", "hex")
        print(f"十六进制数据: '48656C6C6F' -> {result}")
    except Exception as e:
        print(f"十六进制数据测试失败: {e}")

    # 测试空十六进制
    try:
        result = format_data_for_send("", "hex")
        print(f"空十六进制: '' -> {result}")
    except Exception as e:
        print(f"空十六进制测试失败: {e}")


def test_request_model():
    """测试请求模型"""
    print("\n=== 测试请求模型 ===")

    # 测试正常请求
    try:
        req = SendDataRequest(data="Hello", format="text")
        print(f"正常请求: data='{req.data}', format='{req.format}'")
    except Exception as e:
        print(f"正常请求测试失败: {e}")

    # 测试None数据
    try:
        req = SendDataRequest(data=None, format="text")
        print(f"None数据请求: data='{req.data}', format='{req.format}'")
    except Exception as e:
        print(f"None数据请求测试失败: {e}")

    # 测试缺少format
    try:
        req = SendDataRequest(data="Hello")
        print(f"缺少format请求: data='{req.data}', format='{req.format}'")
    except Exception as e:
        print(f"缺少format请求测试失败: {e}")


if __name__ == "__main__":
    test_data_formatting()
    test_request_model()
    print("\n=== 测试完成 ===")
