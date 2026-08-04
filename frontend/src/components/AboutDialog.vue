<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { getAvatar, openExternalUrl, refreshAvatar } from '@/api'
import bundledAvatar from '@/assets/avatar.jpg'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const APP_VERSION = __APP_VERSION__
const GITHUB_REPO = 'https://github.com/soifow/management-prd-vite'
const AUTHOR = 'soifow'

/** 当前显示的头像 src。
 *  - 默认 = bundledAvatar（图片 A：打包内默认）
 *  - 用户访问过仓库后 = 后端缓存的 B
 */
const avatarSrc = ref<string>(bundledAvatar)

/** 防止 dialog 快速开关或多次点击触发并发拉取。 */
let inFlight = false

/** 拉取后端缓存的 B；存在则覆盖默认 A。失败/不存在保持 A 不动（A 永兜底）。 */
async function loadCachedAvatar() {
  if (inFlight) return
  inFlight = true
  try {
    const result = await getAvatar()
    if (result.exists) {
      avatarSrc.value = result.data
    }
  } catch {
    // 静默：A 永远可见
  } finally {
    inFlight = false
  }
}

/** 弹窗首次挂载拉一次；每次重新打开时再拉（保证 B 最新）。 */
onMounted(() => {
  loadCachedAvatar()
})
watch(
  () => props.modelValue,
  (visible) => {
    if (visible) loadCachedAvatar()
  },
)

/** 点击仓库链接：并行触发「打开浏览器」+「刷新 B」，刷新成功后立刻切到 B。 */
async function openRepo() {
  // 1) 主操作：用系统默认浏览器打开仓库（避免在 webview 内导航）
  openExternalUrl(GITHUB_REPO).catch(() => {
    // 降级：直接 window.open（开发模式下 pywebview.api 不可用）
    window.open(GITHUB_REPO, '_blank')
  })

  // 2) 异步刷新缓存的 B（best-effort：网络失败不影响主流程）
  try {
    const result = await refreshAvatar()
    if (result.updated) {
      await loadCachedAvatar()
    } else if (result.reason) {
      // 静默失败，不打扰用户；可在控制台查看
      console.info('刷新头像失败:', result.reason)
    }
  } catch (e) {
    ElMessage.warning(e instanceof Error ? e.message : '刷新头像失败')
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="关于"
    width="380px"
    class="about-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <div class="about-body">
      <!-- 头像：默认 A（打包），访问仓库后切到缓存 B -->
      <img :src="avatarSrc" alt="avatar" class="avatar" />
      <h2 class="app-name">需求记录</h2>
      <p class="version">v{{ APP_VERSION }}</p>

      <el-divider />

      <dl class="info-list">
        <dt>作者</dt>
        <dd>{{ AUTHOR }}</dd>
        <dt>仓库</dt>
        <dd>
          <el-link type="primary" :underline="false" @click="openRepo">
            {{ GITHUB_REPO }}
          </el-link>
        </dd>
        <dt>技术栈</dt>
        <dd>Vue 3 + Vite + PyWebView + PyInstaller</dd>
        <dt>许可</dt>
        <dd>MIT</dd>
      </dl>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">关闭</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.about-body {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 8px 0;
}
.avatar {
  width: 80px;
  height: 80px;
  border-radius: 50%;
  object-fit: cover;
  border: 2px solid #e5e7eb;
  margin-bottom: 12px;
}
.app-name {
  margin: 0;
  font-size: 20px;
  font-weight: 600;
  color: #1f2937;
}
.version {
  margin: 4px 0 0;
  font-size: 13px;
  color: #6b7280;
}
.el-divider {
  width: 100%;
  margin: 16px 0;
}
.info-list {
  width: 100%;
  display: grid;
  grid-template-columns: auto 1fr;
  gap: 8px 16px;
  font-size: 14px;
  line-height: 1.6;
}
.info-list dt {
  color: #6b7280;
  white-space: nowrap;
  text-align: right;
}
.info-list dd {
  margin: 0;
  color: #1f2937;
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
}
.info-list .el-link {
  font-size: 13px;
}
</style>
