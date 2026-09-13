import { fileURLToPath, URL } from 'node:url'
import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    host: '127.0.0.1',
    port: 5173,
    cacheDir: process.env.VITE_CACHE_DIR || 'C:/Users/26912/AppData/Local/Temp/healthybot-vite-cache',
    proxy: {
      // 开发环境代理：前端请求 /api 转发到 FastAPI :8000
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: true,
      },
    },
  },
})
