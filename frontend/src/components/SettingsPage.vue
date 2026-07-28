<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Folder, Sort } from '@element-plus/icons-vue'

import { useSettingsStore } from '@/stores/settings'
import type { ViewMode } from '@/types/settings'

const emit = defineEmits<{
  (e: 'save'): void
  (e: 'cancel'): void
}>()

const settingsStore = useSettingsStore()
const { storageInfo, loading, defaultViewMode, settingsOrder } = storeToRefs(settingsStore)

// 分组注册表（未来追加分组只需在此扩展，合法 key 由此决定）
const GROUPS = [
  { key: 'storage', label: '存储位置' },
  { key: 'display', label: '显示设置' },
] as const

// 拖拽编辑态：editingOrder=true 时用 draftOrder 渲染并可拖拽；false 时用已落盘 settingsOrder
const editingOrder = ref(false)
const draftOrder = ref<string[]>([...settingsOrder.value])
const dragKey = ref<string | null>(null)
const dragOverKey = ref<string | null>(null)

// 实际用于渲染的顺序：编辑态用草稿，非编辑态用已落盘值
const activeOrder = computed(() => (editingOrder.value ? draftOrder.value : settingsOrder.value))

// 按 activeOrder 排序的分组（容错：过滤未知 key、补齐缺失 key）
const sortedGroups = computed(() => {
  const validKeys = new Set<string>(GROUPS.map((g) => g.key))
  const ordered = activeOrder.value
    .filter((k) => validKeys.has(k))
    .map((k) => GROUPS.find((g) => g.key === k)!)
  const seen = new Set(ordered.map((g) => g.key))
  const missing = GROUPS.filter((g) => !seen.has(g.key))
  return [...ordered, ...missing]
})

const activeKey = ref<string>(GROUPS[0].key)
const scrollRef = useTemplateRef<HTMLDivElement>('scrollRef')

onMounted(async () => {
  await settingsStore.loadStorageInfo()
  await nextTick()
  if (scrollRef.value) scrollRef.value.scrollTop = 0
})

function scrollToGroup(key: string) {
  // 编辑态下禁用点击滚动（避免与拖拽冲突）
  if (editingOrder.value) return
  activeKey.value = key
  const el = document.getElementById(`setting-section-${key}`)
  if (el) el.scrollIntoView({ behavior: 'smooth', block: 'start' })
}

// scroll-spy：滚动时高亮当前可见分组（按排序后的分组）
function onScroll() {
  if (editingOrder.value) return
  const container = scrollRef.value
  if (!container) return
  const top = container.scrollTop
  let current: string = sortedGroups.value[0]?.key ?? GROUPS[0].key
  for (const g of sortedGroups.value) {
    const el = document.getElementById(`setting-section-${g.key}`)
    if (!el) continue
    if (el.offsetTop - 12 <= top) current = g.key
  }
  activeKey.value = current
}

// ── 分组顺序拖拽（HTML5 DnD）──
function onToggleOrder() {
  if (editingOrder.value) {
    // 完成：落盘 draftOrder
    finishOrderEdit()
    return
  }
  // 进入编辑态：用当前已落盘顺序初始化草稿
  draftOrder.value = [...settingsOrder.value]
  editingOrder.value = true
}

async function finishOrderEdit() {
  try {
    await settingsStore.saveSettingsOrder(draftOrder.value)
    editingOrder.value = false
    dragKey.value = null
    dragOverKey.value = null
    ElMessage.success('分组顺序已保存')
  } catch (e) {
    // 落盘失败：回滚草稿为已落盘值，保留编辑态供重试
    draftOrder.value = [...settingsOrder.value]
    ElMessage.error(e instanceof Error ? e.message : '保存顺序失败')
  }
}

function onDragStart(key: string) {
  dragKey.value = key
}

function onDragOver(key: string, e: DragEvent) {
  if (!editingOrder.value || dragKey.value === null || dragKey.value === key) return
  e.preventDefault()
  dragOverKey.value = key
}

function onDrop(key: string, e: DragEvent) {
  if (!editingOrder.value || dragKey.value === null || dragKey.value === key) {
    dragKey.value = null
    dragOverKey.value = null
    return
  }
  e.preventDefault()
  const from = draftOrder.value.indexOf(dragKey.value)
  const to = draftOrder.value.indexOf(key)
  if (from === -1 || to === -1) return
  const next = [...draftOrder.value]
  next.splice(from, 1)
  next.splice(to, 0, dragKey.value)
  draftOrder.value = next
  dragKey.value = null
  dragOverKey.value = null
}

function onDragEnd() {
  dragKey.value = null
  dragOverKey.value = null
}

// 更改存储位置：选目录 → 二次确认 → 迁移
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

// 保存：仅落盘「默认聚合方式」，不回写主界面当前视图（二者解耦：默认值只在冷启动生效）
async function onSave() {
  try {
    await settingsStore.saveDefaultViewMode(defaultViewMode.value as ViewMode)
    emit('save')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存设置失败')
  }
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
          v-for="g in sortedGroups"
          :key="g.key"
          class="tab"
          :class="{
            active: activeKey === g.key,
            'tab-editing': editingOrder,
            'tab-dragging': dragKey === g.key,
            'tab-drag-over': dragOverKey === g.key && dragKey !== g.key,
          }"
          :draggable="editingOrder"
          @click="scrollToGroup(g.key)"
          @dragstart="onDragStart(g.key)"
          @dragover="onDragOver(g.key, $event)"
          @drop="onDrop(g.key, $event)"
          @dragend="onDragEnd"
        >
          <el-icon v-if="editingOrder" class="drag-handle"><Sort /></el-icon>
          <span class="tab-label">{{ g.label }}</span>
        </div>
        <div v-if="editingOrder" class="edit-hint">拖拽手柄调整顺序</div>
      </div>

      <!-- 右：单一可滚动容器 -->
      <div ref="scrollRef" class="scroll-area" @scroll.passive="onScroll">
        <section
          v-for="g in sortedGroups"
          :key="g.key"
          :id="`setting-section-${g.key}`"
          class="settings-card"
        >
          <!-- 存储位置 -->
          <template v-if="g.key === 'storage'">
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
          </template>

          <!-- 显示设置 -->
          <template v-else-if="g.key === 'display'">
            <h3 class="section-title">显示设置</h3>
            <p class="section-desc">
              设置需求列表的默认聚合方式（程序冷启动时生效）。此设置与主界面当前的聚合切换相互独立——主界面切换不会修改这里的默认值。
            </p>
            <el-form label-position="top">
              <el-form-item label="默认聚合方式">
                <el-radio-group v-model="defaultViewMode">
                  <el-radio value="date">按时间</el-radio>
                  <el-radio value="module">按模块</el-radio>
                </el-radio-group>
              </el-form-item>
            </el-form>
          </template>
        </section>
      </div>
    </div>

    <footer class="page-footer">
      <el-button @click="onToggleOrder">
        <el-icon><Sort /></el-icon>
        {{ editingOrder ? '完成' : '顺序' }}
      </el-button>
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
  background: #f5f7fa;
  border-left: 1px solid #e5e7eb;
}
.page-header {
  flex-shrink: 0;
  /* 整个 header 白底（全宽），底部 border 与下方内容分隔 */
  background: #ffffff;
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
  /* 左/上 padding 去掉：tabs 贴左边、内容顶格；间距由 tabs 与 scroll-area 的 gap 及卡片内边距提供 */
  padding: 0;
  gap: 16px;
}
.tabs {
  width: 160px;
  flex-shrink: 0;
  background: #ffffff;
  border-right: 1px solid #e5e7eb;
  padding-right: 8px;
}
.tab {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  font-size: 14px;
  color: #374151;
  margin-bottom: 4px;
  transition: background 0.15s;
  border: 1px solid transparent;
}
.tab:hover {
  background: #f3f4f6;
}
.tab.active {
  background: #ecf5ff;
  color: #409eff;
  font-weight: 600;
}
.tab-editing {
  cursor: grab;
}
.tab-editing:active {
  cursor: grabbing;
}
.drag-handle {
  color: #9ca3af;
  flex-shrink: 0;
}
.tab-label {
  flex: 1;
}
.tab-dragging {
  opacity: 0.4;
}
.tab-drag-over {
  border-top: 2px solid #409eff;
}
.edit-hint {
  margin-top: 8px;
  font-size: 12px;
  color: #9ca3af;
  text-align: center;
}
.scroll-area {
  flex: 1;
  overflow-y: auto;
  min-width: 0;
  scroll-behavior: smooth;
  /* 左缘间距已由 tabs 与 scroll-area 之间的 gap 提供，左 padding 置 0；上/右/下留灰让卡片浮起 */
  padding: 16px 16px 16px 0;
  background: transparent;
  border-radius: 0;
}
.settings-card {
  background: #ffffff;
  border: 1px solid #e5e7eb;
  border-radius: 8px;
  padding: 16px 20px;
  margin-bottom: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
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
