import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'

// 独立打包产品官网 Demo：产出单页静态文件，便于直接发给用户预览
export default defineConfig({
  plugins: [vue()],
  base: './',
  build: {
    outDir: 'marketing-dist',
    emptyOutDir: true,
    assetsInlineLimit: 100000000,
    rollupOptions: {
      input: 'D:/项目阶段/项目实操/智能健康测评/frontend/marketing-standalone/index.html',
    },
  },
})
