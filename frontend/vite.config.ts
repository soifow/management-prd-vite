import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'

import { defineConfig } from 'vitest/config'
import vue from '@vitejs/plugin-vue'
import Icons from 'unplugin-icons/vite'

// __APP_VERSION__ 的全项目唯一真相源是 pyproject.toml（[project] version）；
// package.json 的 version 仅为 npm 约定，不再用于展示，避免两处手动维护漂移。
const pkg = JSON.parse(readFileSync(new URL('./package.json', import.meta.url), 'utf-8'))
const pyproject = readFileSync(new URL('../pyproject.toml', import.meta.url), 'utf-8')
// 锚定行首的裸 `version = "..."`（pyproject.toml 中仅 [project] 段为此形式）。
const m = pyproject.match(/^\s*version\s*=\s*"([^"]+)"/m)
const APP_VERSION = m ? m[1] : pkg.version

// https://vite.dev/config/
export default defineConfig({
  // unplugin-icons：编译时按需把 ~icons/{set}/{name} 解析成 Vue 组件，离线打包内联 SVG。
  // 不开 autoInstall，依赖由 pnpm 显式管理（已装 @iconify-json/pixelarticons）。
  plugins: [vue(), Icons({})],
  define: {
    __APP_VERSION__: JSON.stringify(APP_VERSION),
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
