import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import 'element-plus/dist/index.css'
import { config } from 'md-editor-v3'
import 'md-editor-v3/lib/style.css'

import App from './App.vue'
import './styles/main.css'

// 关闭 md-editor-v3 的 linkShortener 扩展：它会将含斜杠(/)的长文本（如"已完成/待对接"）
// 误判为链接并在超过 30 字符时折叠为 "..."，点击展开后光标进入又缩回，影响正常编辑。
config({
  codeMirrorExtensions(exs) {
    return exs.filter((e) => e.type !== 'linkShortener')
  },
})

const app = createApp(App)

app.use(createPinia())
app.use(ElementPlus)
app.mount('#app')
