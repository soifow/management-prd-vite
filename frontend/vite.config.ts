import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'

// https://vite.dev/config/
export default defineConfig({
  plugins: [vue()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    // PyWebView 开发模式固定加载 http://localhost:5173，端口必须稳定
    port: 5173,
    strictPort: true,
  },
  // PyWebView 生产模式用 file:// 协议加载本地 dist/index.html，必须用相对路径，
  // 否则 /assets/... 会解析到盘符根目录而 404（窗口空白）。
  base: './',
  build: {
    outDir: 'dist',
    emptyOutDir: true,
  },
  test: {
    environment: 'jsdom',
    globals: true,
    include: ['src/**/__tests__/**/*.spec.ts'],
  },
})
