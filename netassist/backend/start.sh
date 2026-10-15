#!/bin/bash

# 网络调试助手后端启动脚本

echo "🚀 启动网络调试助手后端服务..."

# 检查Python环境
if ! command -v python3 &> /dev/null; then
    echo "❌ Python3 未安装，请先安装Python3"
    exit 1
fi

# 进入后端目录
cd "$(dirname "$0")"

# 检查依赖是否安装
if ! python3 -c "import fastapi" &> /dev/null; then
    echo "📦 正在安装依赖..."
    pip3 install -r requirements.txt
fi

# 启动服务
echo "🌐 启动服务: http://0.0.0.0:8000"
echo "📚 API文档: http://0.0.0.0:8000/docs"
echo "按 Ctrl+C 停止服务"
echo ""

python3 main.py