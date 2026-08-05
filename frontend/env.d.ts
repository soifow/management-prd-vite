/// <reference types="vite/client" />

/** 由 vite.config.ts define 注入，值来自 package.json version */
declare const __APP_VERSION__: string

/** Lottie 动画资源经 Vite `?url` 导入为打包后的资源 URL（dotlottie-vue 的 :src 用）。 */
declare module '*.lottie?url' {
  const src: string
  export default src
}
