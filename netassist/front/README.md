# 网络调试助手前端

基于Vue3 + Element Plus构建的现代化Web界面，提供网络和串口调试功能。

## 项目结构

```
front/
├── index.html              # HTML入口文件
├── package.json            # 项目配置和依赖管理
├── vite.config.js          # Vite构建配置
├── src/
│   ├── App.vue             # 根组件
│   ├── main.js             # 应用入口
│   ├── router/             # 路由配置
│   ├── views/              # 页面组件
│   ├── components/         # 通用组件
│   └── api/                # API请求封装
```

## 技术栈

- **前端框架**: Vue 3
- **UI组件库**: Element Plus
- **路由管理**: Vue Router 4
- **构建工具**: Vite
- **图标库**: @element-plus/icons-vue

## 功能特性

### 🌐 网络调试页面
- TCP客户端/服务器模式切换
- UDP通信支持
- 数据收发区域实时显示
- 文本/十六进制格式切换
- 连接状态实时监控

### 🔌 串口调试页面
- 自动扫描可用串口
- 串口参数配置（波特率、数据位、停止位、校验位）
- 数据收发区域实时显示
- 文本/十六进制格式切换
- 连接状态实时监控

### 🎨 用户界面
- 响应式设计，支持桌面和移动设备
- 左侧菜单栏导航
- 现代化UI组件
- 数据实时更新

## 快速开始

### 安装依赖

```bash
cd front
npm install
```

### 开发模式运行

```bash
npm run dev
```

访问 http://localhost:5173 查看开发版本

### 构建生产版本

```bash
npm run build
```

构建后的文件将生成在 `dist` 目录中

### 预览生产版本

```bash
npm run preview
```

## 项目配置

### 环境变量

项目支持通过环境变量配置API地址：

```
VITE_API_BASE_URL=http://localhost:20001/api
VITE_WS_BASE_URL=ws://localhost:20001/ws
```

### Vite配置

可在 `vite.config.js` 中修改构建配置：

```javascript
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

export default defineConfig({
  plugins: [vue()],
  server: {
    port: 5173,  // 开发服务器端口
    proxy: {
      // 代理配置（如果需要）
    }
  },
  build: {
    outDir: 'dist',  // 构建输出目录
    assetsDir: 'assets'  // 静态资源目录
  }
})
```

## 代码规范

- 使用Vue 3的Composition API
- 组件命名采用PascalCase
- 遵循Vue的单文件组件规范
- 路由配置清晰明了

## 部署说明

### 独立部署

构建完成后，可将 `dist` 目录中的文件部署到任何Web服务器上：

- Nginx
- Apache
- Caddy
- 或任何支持静态文件的服务器

### 与后端集成

前端构建后的文件也可以部署到后端的静态文件目录中，实现前后端一体化部署。

## 开发指南

### 添加新页面

1. 在 `src/views/` 目录下创建新的Vue组件
2. 在 `src/router/index.js` 中添加路由配置
3. 在 `src/App.vue` 的侧边栏中添加菜单项

### 添加新组件

1. 在 `src/components/` 目录下创建新的Vue组件
2. 在需要使用的地方导入并注册组件

### API调用

1. 在 `src/api/` 目录下创建或使用现有的API封装文件
2. 导入并使用API函数进行后端通信

## 常见问题

### 开发服务器无法访问后端API

请检查API地址配置是否正确，并确保后端服务正在运行。

### 构建后的页面无法正常显示

检查是否有静态资源路径问题，可在 `vite.config.js` 中配置 `base` 选项。

### WebSocket连接失败

请检查WebSocket地址配置和网络连接是否正常。