<script setup lang="ts">
import { computed, nextTick, onMounted, ref, useTemplateRef, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { IPixelFolder, IPixelSortVertical } from '@/constants/icons'

import { useSettingsStore } from '@/stores/settings'
import { whenReady } from '@/api'
import { moveKey, normalizeOrder } from '@/utils/settingsOrder'
import type { ProjectListDateMode, ViewMode } from '@/types/settings'

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
  { key: 'reminder', label: '提醒设置' },
  { key: 'subitem', label: '子需求进度' },
] as const
// 全部已注册分组的 key（规范化顺序与拖拽重排的合法集合；新增分组自动纳入）
const GROUP_KEYS = GROUPS.map((g) => g.key)

// 项目列表「最新」日期口径下拉选项：value/label/desc，desc 随选中项联动显示
const DATE_MODE_OPTIONS: { value: ProjectListDateMode; label: string; desc: string }[] = [
  {
    value: 'latest_any',
    label: '最新需求日期',
    desc: '取项目内所有需求日期的最新值，不限状态。新增任意需求（含待办/进行中）都会刷新该日期。',
  },
  {
    value: 'latest_done',
    label: '最新已完成日期',
    desc: '只统计「已完成/等待对接」状态的需求日期，反映项目最近一次完成或等待对接的时间点。',
  },
  {
    value: 'latest_activity',
    label: '最近操作时间',
    desc: '取项目最近一次新增/编辑/删除需求（或重命名）的时间。任何改动都会把该项目顶到最新。',
  },
]

// 拖拽编辑态：editingOrder=true 时用 draftOrder 渲染并可拖拽；false 时用已落盘 settingsOrder
const editingOrder = ref(false)
const draftOrder = ref<string[]>([...settingsOrder.value])
const dragKey = ref<string | null>(null)
const dragOverKey = ref<string | null>(null)

// 提醒设置草稿（保存时一并落盘）
const draftThreshold = ref(settingsStore.reminderThresholdDays)
const draftUrgentThreshold = ref(settingsStore.urgentThresholdDays)
const draftReminderColor = ref(settingsStore.reminderWarningColor)
const draftUrgentColor = ref(settingsStore.urgentWarningColor)
const draftShowNoDeadline = ref(settingsStore.showNoDeadlineInTodo)
// 子需求进度草稿
const draftShowSubitemProgress = ref(settingsStore.showSubitemProgressInTree)

// 项目列表日期口径草稿（保存时一并落盘）
const draftProjectListDateMode = ref<ProjectListDateMode>(settingsStore.projectListDateMode)

// 紧急阈值必定 ≤ 提醒阈值：当提醒阈值被下调到低于当前紧急阈值时，
// 自动把紧急阈值对齐到提醒阈值（后端校验器同样拒绝前者 > 后者）。
watch(draftThreshold, (t) => {
  if (draftUrgentThreshold.value > t) {
    draftUrgentThreshold.value = t
  }
})

// 当前选中口径的说明文字（随下拉选项联动）
const dateModeDesc = computed(
  () => DATE_MODE_OPTIONS.find((o) => o.value === draftProjectListDateMode.value)?.desc ?? '',
)

// 实际用于渲染的顺序：编辑态用草稿，非编辑态用已落盘值
const activeOrder = computed(() => (editingOrder.value ? draftOrder.value : settingsOrder.value))

// 按 activeOrder 排序的分组（规范化：过滤未知 key、补齐缺失 key）
const sortedGroups = computed(() =>
  normalizeOrder(activeOrder.value, GROUP_KEYS).map((k) => GROUPS.find((g) => g.key === k)!),
)

const activeKey = ref<string>(GROUPS[0].key)
const scrollRef = useTemplateRef<HTMLDivElement>('scrollRef')

onMounted(async () => {
  // 视图用 v-show 常驻、应用挂载即触发本钩子；须先等待桥接就绪再调后端，
  // 否则与 App.vue 的 whenReady 并发执行时桥接尚未注入会抛 ApiError。
  await whenReady()
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
  // 进入编辑态：用当前已落盘顺序初始化草稿，并规范化补齐全部分组 key。
  // 关键：旧版本持久化的 settings_order 可能只含部分 key，若不补齐，缺失的
  // 分组虽能渲染但 draftOrder.indexOf() 返回 -1，导致 onDrop 静默失败无法重排。
  draftOrder.value = normalizeOrder([...settingsOrder.value], GROUP_KEYS)
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
  // 经 normalizeOrder 保证 draftOrder 始终包含 GROUP_KEYS 全部 key，
  // 因此缺失 key 导致 onDrop 失败的场景不再出现。
  draftOrder.value = moveKey(draftOrder.value, dragKey.value, key)
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

// 保存：落盘「默认聚合方式」+「项目列表日期口径」+「提醒设置」，
// 不回写主界面当前视图（二者解耦：默认值只在冷启动生效）
async function onSave() {
  try {
    await settingsStore.saveDefaultViewMode(defaultViewMode.value as ViewMode)
    await settingsStore.saveProjectListDateMode(draftProjectListDateMode.value)
    await settingsStore.saveReminderSettings(
      draftThreshold.value,
      draftUrgentThreshold.value,
      draftReminderColor.value,
      draftUrgentColor.value,
      draftShowNoDeadline.value,
    )
    await settingsStore.saveSubitemProgressInTree(draftShowSubitemProgress.value)
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
          <el-icon v-if="editingOrder" class="drag-handle"><IPixelSortVertical /></el-icon>
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
                  :icon="IPixelFolder"
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
              <el-form-item label="项目列表日期">
                <el-select
                  v-model="draftProjectListDateMode"
                  style="width: 240px"
                  placeholder="选择日期口径"
                >
                  <el-option
                    v-for="opt in DATE_MODE_OPTIONS"
                    :key="opt.value"
                    :label="opt.label"
                    :value="opt.value"
                  />
                </el-select>
                <p class="field-hint date-mode-desc">{{ dateModeDesc }}</p>
              </el-form-item>
            </el-form>
          </template>

          <!-- 提醒设置 -->
          <template v-else-if="g.key === 'reminder'">
            <h3 class="section-title">提醒设置</h3>
            <p class="section-desc">
              启动时待办提醒抽屉中只显示「剩余天数 ≤ 提醒阈值」且未完成的需求；「已逾期」始终置顶，状态为「暂缓」的项目不受阈值影响并始终显示在「远期规划」组。紧急阈值内的聚合标题栏用深红色背景，提醒阈值内的用橙色背景。
            </p>
            <el-form label-position="top">
              <el-form-item label="提醒阈值（天）">
                <el-input-number
                  v-model="draftThreshold"
                  :min="0"
                  :max="365"
                  :step="1"
                  style="width: 160px"
                />
                <span class="field-hint">仅剩余天数 ≤ 该值（且未完成）进入待办；0 表示只显示已逾期</span>
              </el-form-item>
              <el-form-item label="紧急阈值（天）">
                <el-input-number
                  v-model="draftUrgentThreshold"
                  :min="0"
                  :max="draftThreshold"
                  :step="1"
                  style="width: 160px"
                />
                <span class="field-hint">剩余天数 ≤ 该值的聚合标题栏用紧急警告色；应 ≤ 提醒阈值</span>
              </el-form-item>
              <el-form-item label="提醒警告色">
                <el-color-picker v-model="draftReminderColor" :show-alpha="false" />
                <span class="field-hint">提醒阈值内聚合标题栏的背景色</span>
              </el-form-item>
              <el-form-item label="紧急警告色">
                <el-color-picker v-model="draftUrgentColor" :show-alpha="false" />
                <span class="field-hint">紧急阈值内聚合标题栏的背景色</span>
              </el-form-item>
              <el-form-item label="无时限需求">
                <el-switch v-model="draftShowNoDeadline" />
                <span class="field-hint">开启时，未设置完成时限的未完成需求常驻待办列表</span>
              </el-form-item>
            </el-form>
          </template>

          <!-- 子需求进度 -->
          <template v-else-if="g.key === 'subitem'">
            <h3 class="section-title">子需求进度</h3>
            <p class="section-desc">
              控制树形功能节点是否显示子需求完成进度（done/total）。关闭时仅在功能详情页显示子需求进度信息。
            </p>
            <el-form label-position="top">
              <el-form-item label="树形显示子需求进度">
                <el-switch v-model="draftShowSubitemProgress" />
                <span class="field-hint">开启时，树形功能节点追加 (完成数/总数) 进度显示</span>
              </el-form-item>
            </el-form>
          </template>
        </section>
      </div>
    </div>

    <footer class="page-footer">
      <el-button @click="onToggleOrder">
        <el-icon><IPixelSortVertical /></el-icon>
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
.field-hint {
  margin-left: 12px;
  font-size: 12px;
  color: #9ca3af;
  line-height: 1.6;
}
/* 日期口径说明：独立一行，紧贴下拉框下方 */
.date-mode-desc {
  margin-left: 0;
  margin-top: 8px;
  margin-bottom: 0;
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
