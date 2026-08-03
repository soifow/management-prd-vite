/// unplugin-icons 虚拟模块类型声明（~icons/{set}/{name}）
declare module '~icons/*' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<{}, {}, any>
  export default component
}
