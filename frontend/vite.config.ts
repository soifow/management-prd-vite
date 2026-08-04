import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import Icons from 'unplugin-icons/vite'

// 读取 package.json 版本，注入 __APP_VERSION__ 供「关于」弹窗展示，避免硬编码版本号不同步。
const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))

// https://vite.dev/config/
export default defineConfig({
  // unplugin-icons：编译时按需把 ~icons/{set}/{name} 解析成 Vue 组件，离线打包内联 SVG。
  // 不开 autoInstall，依赖由 pnpm 显式管理（已装 @iconify-json/pixelarticons）。
  plugins: [vue(), Icons({})],
  define: {
    __APP_VERSION__: JSON.stringify(pkg.version),
  },
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
