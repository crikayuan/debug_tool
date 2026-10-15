# 网络调试助手后端API

基于FastAPI构建的高性能后端服务，支持TCP/UDP和串口通信功能。

## 项目结构

```
backend/
├── main.py              # 主入口文件
├── app.py               # FastAPI应用配置
├── config.py            # 配置文件
├── models.py            # 数据模型定义
├── requirements.txt     # 依赖管理
├── net-debug-tools.spec       # PyInstaller打包配置
├── routes/             # 路由模块
│   ├── __init__.py
│   ├── net.py          # 网络相关功能（集成TCP和UDP）
│   ├── serial.py       # 串口相关路由
│   ├── websocket.py    # WebSocket路由
│   └── system.py       # 系统管理功能
├── services/           # 业务逻辑服务
│   ├── __init__.py
│   ├── net_service.py    # 网络连接管理服务（支持TCP和UDP）
│   └── serial_service.py # 串口连接管理服务
├── utils/                # 工具函数
│   ├── __init__.py
│   └── data_utils.py   # 数据处理工具
├── static/             # 静态文件目录
│   ├── assets/
│   └── index.html
└── test/               # 测试文件
    ├── test_fix.py
    └── test_tcp_server.py
```

## 核心功能

### 🌐 网络通信服务
- **统一网络服务**: 支持TCP和UDP协议，统一集成到net_service中
- 客户端/服务器模式支持
- 多连接管理
- 实时数据传输（WebSocket支持）
- 连接状态监控和统计
- **UDP服务**: 支持数据包收发和多端口监听
- **WebSocket服务**: 实时数据传输，支持多客户端
- **连接管理**: 统一的连接创建、维护、关闭机制

### 🔌 串口通信服务
- **串口扫描**: 自动检测系统可用串口
- **参数配置**: 支持自定义波特率、数据位等参数
- **数据传输**: 高效的串口数据读写
- **错误处理**: 完善的异常捕获和处理机制

### 🛠️ 系统服务
- **配置管理**: 统一的配置加载和持久化
- **健康检查**: 系统状态监控
- **日志服务**: 结构化日志记录
- **API文档**: 自动生成的Swagger和ReDoc文档

### 📦 部署支持
- **PyInstaller打包**: 支持生成独立可执行文件
- **systemd集成**: 支持Linux系统服务管理
- **静态文件服务**: 集成前端构建文件提供

## 技术栈

- **Web框架**: FastAPI
- **ASGI服务器**: Uvicorn
- **网络通信**: Python标准库socket
- **串口通信**: pyserial
- **API文档**: Swagger UI, ReDoc
- **打包工具**: PyInstaller

## 主要改进

### 1. 模块化结构
- **routes/**: 将路由按功能分离，提高代码可维护性
- **services/**: 业务逻辑与路由分离，便于测试和复用
- **utils/**: 通用工具函数，提高代码复用率
- **models.py**: 统一的数据模型定义
- **config.py**: 集中的配置管理

### 2. 代码优化
- 移除全局变量，使用服务类管理连接状态
- 统一的API响应格式
- 更好的错误处理和异常管理
- 类型提示增强代码可读性

### 3. 功能增强
- 健康检查端点 `/health`
- 更详细的连接统计信息
- WebSocket心跳机制
- 数据格式验证和转换
- 支持二进制和文本格式数据传输

### 4. 部署优化
- PyInstaller打包配置完善
- systemd服务集成
- 环境变量配置支持
- 多平台兼容性改进

## 安装与运行

### 1. 安装依赖
```bash
cd backend
pip install -r requirements.txt
```

### 2. 运行服务

**直接运行主文件：**
```bash
python main.py
```

**使用Uvicorn运行：**
```bash
uvicorn main:app --host 0.0.0.0 --port 20001
```

### 3. 开发模式运行
```bash
uvicorn main:app --host 0.0.0.0 --port 20001 --reload
```

### 4. 使用环境变量配置
```bash
# 设置服务端口
PORT=20001 \
# 设置调试模式
DEBUG=true \
# 运行服务
python main.py
```

## API文档

启动服务后访问以下地址查看自动生成的API文档：
- Swagger UI: http://localhost:20001/docs
- ReDoc: http://localhost:20001/redoc

## 主要端点

### TCP相关
- `POST /api/tcp/connect` - 建立TCP连接
  - 支持客户端和服务器模式
  - 可配置主机、端口、超时等参数
- `POST /api/tcp/disconnect/{connection_id}` - 断开TCP连接
- `POST /api/tcp/send/{connection_id}` - 发送TCP数据
  - 支持文本和十六进制格式
- `GET /api/tcp/status/{connection_id}` - 获取TCP连接状态
- `GET /api/tcp/connections` - 获取所有TCP连接列表

### UDP相关
- `POST /api/udp/open` - 打开UDP端口
- `POST /api/udp/close/{port}` - 关闭UDP端口
- `POST /api/udp/send` - 发送UDP数据
- `GET /api/udp/status/{port}` - 获取UDP端口状态

### 串口相关
- `GET /api/serial/ports` - 获取可用串口列表
- `POST /api/serial/connect` - 打开串口连接
  - 可配置波特率、数据位、停止位、校验位等
- `POST /api/serial/disconnect/{port}` - 关闭串口连接
- `POST /api/serial/send/{port}` - 发送串口数据
- `GET /api/serial/status/{port}` - 获取串口连接状态

### WebSocket
- `WS /ws/tcp/{connection_id}` - TCP实时数据传输
- `WS /ws/udp/{port}` - UDP实时数据传输
- `WS /ws/serial/{port}` - 串口实时数据传输

### 系统
- `GET /` - API信息
- `GET /health` - 健康检查
- `GET /api/system/status` - 获取系统状态
- `GET /api/system/logs` - 获取系统日志

### 网络功能
- `GET /api/net/interfaces` - 获取网络接口信息
- `GET /api/net/dns` - 获取DNS配置
- `POST /api/net/ping` - 执行Ping测试
- `POST /api/net/traceroute` - 执行Traceroute测试

## 配置说明

### 配置文件

可在 `config.py` 中修改以下配置：
- 服务器地址和端口
- CORS设置
- WebSocket配置
- 日志级别和格式
- 静态文件路径
- 超时设置

### 环境变量

支持通过环境变量覆盖配置文件的设置：
- `PORT` - 服务器端口 (默认: 20001)
- `HOST` - 服务器主机 (默认: 0.0.0.0)
- `DEBUG` - 调试模式 (默认: False)
- `LOG_LEVEL` - 日志级别 (默认: INFO)
- `STATIC_DIR` - 静态文件目录

### 配置示例

```python
# config.py示例配置

class Config:
    # 服务器配置
    HOST = "0.0.0.0"
    PORT = 20001
    DEBUG = False
    
    # 日志配置
    LOG_LEVEL = "INFO"
    LOG_FORMAT = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    
    # 静态文件配置
    STATIC_DIR = "./static"
    
    # WebSocket配置
    WS_MAX_SIZE = 1024 * 1024  # 1MB
    WS_PING_INTERVAL = 30      # 30秒
    
    # 连接配置
    TCP_TIMEOUT = 30           # 30秒
    SERIAL_TIMEOUT = 0.1       # 0.1秒
```

## 测试

项目包含单元测试和集成测试：

```bash
# 运行所有测试
cd backend
python -m pytest

# 运行特定测试
python -m pytest test/test_tcp_server.py
```

## 打包部署

### 1. 使用PyInstaller打包

```bash
# 在项目根目录执行
./build-binary.sh
```

打包后的可执行文件将位于 `dist/net-debug-tools`

### 2. 构建deb包

```bash
# 在项目根目录执行
./build-deb.sh
```

构建后的deb包将位于 `build/net-debug-tools.deb`

### 3. 安装服务

```bash
# 在项目根目录执行
./install.sh
```

### 4. 服务管理

安装deb包后，可使用 `net-debug-tools` 命令管理服务：

```bash
net-debug-tools start      # 启动服务
net-debug-tools stop       # 停止服务
net-debug-tools restart    # 重启服务
net-debug-tools status     # 查看状态
net-debug-tools logs       # 查看日志
```

## 开发指南

### 代码规范
- 使用Python 3.8+ 语法
- 遵循PEP 8编码规范
- 使用类型提示增强代码可读性
- 添加适当的注释和文档字符串

### 目录结构规范
- 路由文件放在 `routes/` 目录，只处理请求和响应
- 业务逻辑放在 `services/` 目录，实现核心功能
- 工具函数放在 `utils/` 目录，提供通用功能
- 数据模型放在 `models.py`，定义数据结构

### 添加新功能

1. 在 `models.py` 中定义相关数据模型
2. 在 `services/` 目录创建对应的服务类
3. 在 `routes/` 目录创建对应的路由文件
4. 在 `app.py` 中注册新的路由

## 常见问题

### 端口占用
如果启动服务时出现端口被占用的错误，可以通过以下方式解决：
1. 修改配置文件中的 `PORT` 配置
2. 使用环境变量 `PORT` 指定其他端口

### 串口权限问题
在Linux系统下，可能需要添加用户到dialout组以获取串口访问权限：
```bash
sudo usermod -a -G dialout $USER
```

### 跨域问题
如果前端和后端部署在不同的域名或端口下，可能会遇到跨域问题。确保 `config.py` 中的CORS配置正确。

### WebSocket连接问题
确保WebSocket URL配置正确，并且防火墙允许相应端口的通信。

## 特性

1. **模块化设计**: 代码结构清晰，易于维护和扩展
2. **统一错误处理**: 标准化的API响应格式
3. **类型安全**: 使用Pydantic进行数据验证
4. **实时通信**: WebSocket支持实时数据传输
5. **健康监控**: 内置健康检查和连接状态监控
6. **开发友好**: 支持热重载和自动生成API文档