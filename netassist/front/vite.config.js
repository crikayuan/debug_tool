import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// https://vitejs.dev/config/
export default defineConfig({
    plugins: [vue()],
    server: {
        host: '0.0.0.0',  // 允许外部访问
        port: 3000,
        open: false,      // 服务器环境不自动打开浏览器
        proxy: {
            // 代理所有/api请求到后端服务器
            '/api': {
                target: 'http://localhost:20001',
                changeOrigin: true,
                rewrite: (path) => path
            },
            // 代理WebSocket请求
            '/ws': {
                target: 'ws://localhost:20001',
                ws: true,
                changeOrigin: true
            }
        }
    },
    build: {
        outDir: '../backend/static',  // 构建输出到后端静态文件目录
        emptyOutDir: true,
        assetsDir: 'assets',  // 保持assets目录，但使用相对路径
        rollupOptions: {
            output: {
                manualChunks: {
                    vendor: ['vue', 'vue-router'],
                    elementui: ['element-plus']
                }
            }
        }
    }
})