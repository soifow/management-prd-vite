<script setup lang="ts">
import { nextTick, onMounted, ref, useTemplateRef } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder } from '@element-plus/icons-vue'

import { useSettingsStore } from '@/stores/settings'

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'cancel'): void
}>()

const settingsStore = useSettingsStore()
const { storageInfo, loading } = storeToRefs(settingsStore)

// 分组定义（未来追加分组只需在此扩展）
const groups = [
  { key: 'storage', label: '存储位置' },
] as const

const activeKey = ref<string>(groups[0].key)
const scrollRef = useTemplateRef<HTMLDivElement>('scrollRef')

// 进入设置页：加载存储信息 + 回到首组
onMounted(async () => {
  await settingsStore.loadStorageInfo()
  await nextTick()
  if (scrollRef.value) scrollRef.value.scrollTop = 0
})

function scrollToGroup(key: string) {
  activeKey.value = key
  const el = document.getElementById(`setting-section-${key}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// scroll-spy：滚动时高亮当前可见分组
function onScroll() {
  const container = scrollRef.value
  if (!container) return
  const top = container.scrollTop
  // 找到当前最靠近顶部、尚未滚出的分组
  let current = groups[0].key
  for (const g of groups) {
    const el = document.getElementById(`setting-section-${g.key}`)
    if (!el) continue
    // offsetTop 相对 container
    if (el.offsetTop - 12 <= top) current = g.key
  }
  activeKey.value = current
}

// 更改存储位置：选目录 → 二次确认（提示将创建专属子目录）→ 迁移
async function onChangeStorage() {
  try {
    const picked = await settingsStore.pickFolder()
    if (!picked) return
    await ElMessageBox.confirm(
      `将在所选目录下创建 management-prd-storage 文件夹，并将当前所有数据迁移至该文件夹；旧位置的数据将被清理。\n\n所选目录：${picked}`,
      '更改存储位置',
      { type: 'warning', confirmButtonText: '确认迁移', cancelButtonText: '取消' },
    )
    await settingsStore.migrate(picked)
    ElMessage.success(`已迁移到：${settingsStore.storageInfo?.storage_dir ?? picked}`)
  } catch (e) {
    if (e === 'cancel') return
    ElMessage.error(e instanceof Error ? e.message : '迁移失败')
  }
}

// 保存：当前设置项（存储位置）为即时生效，保存即返回工作区。
// 未来追加的表单型设置在此处统一持久化。
function onSave() {
  emit('save')
}
</script>

<template>
  <section class="settings-page">
    <header class="page-header">
      <h2 class="page-title">设置</h2>
    </header>

    <div class="settings-body">
      <!-- 左：分组标签 -->
      <div class="tabs">
        <div
          v-for="g in groups"
          :key="g.key"
          class="tab"
          :class="{ active: activeKey === g.key }"
          @click="scrollToGroup(g.key)"
        >
          {{ g.label }}
        </div>
      </div>

      <!-- 右：单一可滚动容器 -->
      <div ref="scrollRef" class="scroll-area" @scroll.passive="onScroll">
        <!-- 存储位置 -->
        <section id="setting-section-storage" class="section">
          <h3 class="section-title">存储位置</h3>
          <p class="section-desc">
            程序的数据与配置文件默认存储在此目录。更改时需选择一个父目录，程序会在其下创建 management-prd-storage 专属文件夹并迁入所有数据，旧位置将被清理。
          </p>
          <el-form label-position="top">
            <el-form-item label="当前存储目录">
              <el-input
                :model-value="storageInfo?.storage_dir ?? '加载中…'"
                readonly
                :icon="Folder"
              >
                <template #append>
                  <el-button :loading="loading" @click="onChangeStorage">更改位置</el-button>
                </template>
              </el-input>
            </el-form-item>
            <el-form-item v-if="storageInfo && !storageInfo.is_default">
              <el-tag type="warning" size="small">当前为自定义位置</el-tag>
            </el-form-item>
            <el-form-item v-else-if="storageInfo">
              <el-tag type="info" size="small">默认位置</el-tag>
            </el-form-item>
          </el-form>
        </section>
      </div>
    </div>

    <footer class="page-footer">
      <el-button type="primary" @click="onSave">保存</el-button>
    </footer>
  </section>
</template>

<style scoped>
.settings-page {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-left: 1px solid #e5e7eb;
}
.page-header {
  flex-shrink: 0;
  padding: 16px 24px;
  border-bottom: 1px solid #e5e7eb;
}
.page-title {
  font-size: 18px;
  font-weight: 600;
  margin: 0;
  color: #1f2937;
}
.settings-body {
  display: flex;
  flex: 1;
  min-height: 0;
  padding: 16px 24px 0;
  gap: 16px;
}
.tabs {
  width: 160px;
  flex-shrink: 0;
  border-right: 1px solid #e5e7eb;
  padding-right: 8px;
}
.tab {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #374151;
  margin-bottom: 4px;
  transition: background 0.15s;
}
.tab:hover {
  background: #f3f4f6;
}
.tab.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}
.scroll-area {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  scroll-behavior: smooth;
  padding-bottom: 16px;
}
.section {
  padding-top: 4px;
}
.section-title {
  font-size: 15px;
  font-weight: 600;
  margin: 0 0 6px;
  color: #1f2937;
}
.section-desc {
  font-size: 13px;
  color: #6b7280;
  margin: 0 0 16px;
  line-height: 1.6;
}
.page-footer {
  flex-shrink: 0;
  padding: 12px 24px;
  border-top: 1px solid #e5e7eb;
  display: flex;
  justify-content: flex-end;
  gap: 8px;
  background: #fafafa;
}
</style>
