<script setup lang="ts">
import { computed, nextTick, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElInput, ElMessage, ElMessageBox } from 'element-plus'
import { MdEditor } from 'md-editor-v3'

import { MD_EDITOR_PROPS } from '@/constants/md-editor'
import { IPixelPlus, IPixelTrash } from '@/constants/icons'
import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import { useSettingsStore } from '@/stores/settings'
import type { RequirementStatus, RequirementSubitem } from '@/types'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { formatDate, truncateText } from '@/utils'
import RequirementEditDialog from '@/components/RequirementEditDialog.vue'

const projectsStore = useProjectsStore()
const store = useRequirementsStore()
const settingsStore = useSettingsStore()
const {
  selectedFeature,
  currentIterations,
  selectedIteration,
  selectedIterationId,
  currentSubitems,
  modules,
} = storeToRefs(store)
const { activeProjectId } = storeToRefs(projectsStore)

// 功能名显示截断长度（来自设置；0=不截断）
const featureNameMaxLen = computed(() => settingsStore.featureNameMaxLength)
/** 按设置截断功能名（仅展示用）。 */
function displayFeatureName(name: string): string {
  return truncateText(name, featureNameMaxLen.value)
}

const editVisible = ref(false)

// 编辑缓冲（避免直接改 store 引用）
const bufferContent = ref('')
const bufferStatus = ref<RequirementStatus>('todo')
const bufferModuleNames = ref<string[]>([])
const bufferFeature = ref('')
/** 完成时限缓冲（null = 无时限） */
const bufferDeadline = ref<string | null>(null)
const featureOptions = ref<string[]>([])

// 子需求底部新增态：必须在下方 watch(selectedIteration, {immediate:true}) 之前声明，
// 否则 immediate 回调同步执行时引用到 TDZ 抛 ReferenceError（视图切回重挂时触发）。
const isAddingSubitem = ref(false)
const newSubitemContent = ref('')
const addInputRef = ref<InstanceType<typeof ElInput> | null>(null)

/**
 * 子需求完成时限的乐观本地缓冲：subitemId -> 本地值。
 * 子需求 deadline picker 直绑 store 受控模式时，change 后异步 loadSubitems 回填前，
 * picker 内部值会被旧 :model-value 回退，导致「选了日期但不生效」。
 * 改动先写本地覆盖让 picker 即时反映，后端写入成功后删除该 key 由 store 真值接管。
 */
const subitemDeadlineOverride = ref<Record<string, string | null>>({})

/** 取某子需求当前应显示的 deadline：本地覆盖优先，回退 store 值。 */
function displayDeadline(s: RequirementSubitem): string | null {
  if (s.id in subitemDeadlineOverride.value) return subitemDeadlineOverride.value[s.id]
  return s.completion_deadline
}

// 模块名候选（来自 modules 一等实体表）
const moduleOptions = computed(() => modules.value.map((m) => m.name))

// 按项目拉取已有功能名候选
async function refreshFeatureOptions() {
  if (!activeProjectId.value) {
    featureOptions.value = []
    return
  }
  featureOptions.value = await store.listFeatures(activeProjectId.value)
}

// immediate: 组件从设置页等切回时会被重新挂载（v-if），此时 selectedIteration
// 引用未变、普通 watch 不触发，需立即用当前迭代回填编辑缓冲，否则编辑器显示为空。
watch(
  selectedIteration,
  (it) => {
    if (it) {
      bufferContent.value = it.content
      bufferStatus.value = it.status
      bufferModuleNames.value = [...it.modules]
      bufferFeature.value = it.feature
      bufferDeadline.value = it.completion_deadline
      // 切换迭代时退出底部新增态，避免残留输入跨迭代误写入
      isAddingSubitem.value = false
      newSubitemContent.value = ''
      // 切迭代时清空子需求 deadline 本地覆盖，避免跨迭代残留
      subitemDeadlineOverride.value = {}
      void refreshFeatureOptions()
    }
  },
  { immediate: true },
)

// 暂缓状态联动清空时限（前端即时反馈；后端亦强制）
watch(bufferStatus, (s) => {
  if (s === 'deferred') bufferDeadline.value = null
})

const statusOptions: RequirementStatus[] = [
  'todo',
  'ui_done_waiting_backend',
  'done',
  'deferred',
]

async function onSave() {
  if (!selectedIteration.value) return
  if (bufferModuleNames.value.length === 0) {
    ElMessage.warning('至少选择一个模块')
    return
  }
  try {
    await store.updateIteration(selectedIteration.value.id, {
      module_names: bufferModuleNames.value,
      feature: bufferFeature.value,
      content: bufferContent.value,
      status: bufferStatus.value,
      completion_deadline: bufferDeadline.value ?? undefined,
      clear_completion_deadline: bufferDeadline.value === null,
    })
    ElMessage.success('已保存')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  }
}

function onJumpTo(id: string) {
  void store.selectIteration(id)
}

async function onDeleteIteration(id: string) {
  try {
    await ElMessageBox.confirm('确定删除这条迭代记录？', '删除迭代', { type: 'warning' })
    await store.deleteIteration(id)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

function onNewIteration() {
  editVisible.value = true
}

function onBack() {
  store.closeFeature()
}

// ── 子需求清单区 ──

/** 当前迭代子需求是否全部完成（用于完成提示） */
const allSubitemsDone = computed(
  () =>
    currentSubitems.value.length > 0 &&
    currentSubitems.value.every((s) => s.status === 'done'),
)

// 完成提示守卫（store 持有，切换迭代时重置）
const { completionPromptGuard } = storeToRefs(store)

watch(allSubitemsDone, async (done) => {
  if (!done || completionPromptGuard.value) return
  const cur = currentIterations.value.find((it) => it.id === selectedIterationId.value)
  if (!cur || cur.status === 'done') return
  completionPromptGuard.value = true
  try {
    await ElMessageBox.confirm(
      '当前迭代的子需求已全部完成，是否将该迭代状态改为完成？',
      '同步迭代状态',
      { type: 'success', confirmButtonText: '改为完成', cancelButtonText: '暂不' },
    )
    await store.setIterationStatus(cur.id, 'done')
    ElMessage.success('已同步为完成')
  } catch {
    // 用户取消：guard 已置位，本次停留在该迭代期间不再弹
  }
})

// 子需求底部空行新建（isAddingSubitem / newSubitemContent / addInputRef 已在顶部声明）

// 进入新增态：渲染 textarea 后聚焦
async function startAddSubitem() {
  isAddingSubitem.value = true
  newSubitemContent.value = ''
  await nextTick()
  addInputRef.value?.focus()
}

// 确定：内容非空才写入，空内容视作取消
async function confirmAddSubitem() {
  const itId = selectedIterationId.value
  const content = newSubitemContent.value.trim()
  if (!itId || !content) {
    isAddingSubitem.value = false
    newSubitemContent.value = ''
    return
  }
  try {
    // 默认继承当前迭代（主需求）的完成时限；用户可随后任意修改/删除
    await store.addSubitem(itId, content, 'todo', selectedIteration.value?.completion_deadline ?? null)
    newSubitemContent.value = ''
    isAddingSubitem.value = false
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '添加子需求失败')
  }
}

function cancelAddSubitem() {
  isAddingSubitem.value = false
  newSubitemContent.value = ''
}

async function onSubitemStatusChange(subitemId: string, status: RequirementStatus) {
  try {
    await store.setSubitemStatusItem(subitemId, status)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '更新失败')
  }
}

async function onSubitemDeadlineChange(
  subitemId: string,
  deadline: string | null,
  status: RequirementStatus,
) {
  // 乐观本地覆盖：picker 即时反映新值，避免受控模式下异步回填前的回退
  subitemDeadlineOverride.value = { ...subitemDeadlineOverride.value, [subitemId]: deadline }
  try {
    await store.patchSubitem(subitemId, {
      completion_deadline: deadline ?? undefined,
      clear_completion_deadline: deadline === null,
      status,
    })
    // 成功后由 store 真值接管
    delete subitemDeadlineOverride.value[subitemId]
  } catch (e) {
    // 失败：丢弃本地覆盖，picker 回退到 store 旧值
    delete subitemDeadlineOverride.value[subitemId]
    ElMessage.error(e instanceof Error ? e.message : '更新失败')
  }
}

async function onDeleteSubitem(subitemId: string) {
  try {
    await ElMessageBox.confirm('确定删除这条子需求？', '删除子需求', { type: 'warning' })
    await store.removeSubitem(subitemId)
    ElMessage.success('已删除')
  } catch (e) {
    if (e !== 'cancel') ElMessage.error(e instanceof Error ? e.message : '删除失败')
  }
}

// 当前迭代完成进度（仅展示提示）
const subitemProgressText = computed(() => {
  if (currentSubitems.value.length === 0) return ''
  const done = currentSubitems.value.filter((s) => s.status === 'done').length
  return `${done}/${currentSubitems.value.length} 完成`
})
</script>

<template>
  <div v-if="selectedFeature" class="detail">
    <el-page-header class="head" title="后退" @back="onBack">
      <template #content>
        <span class="title" :title="selectedFeature.feature || ''">
          功能：{{ displayFeatureName(selectedFeature.feature) || '（未命名）' }}
        </span>
      </template>
      <template #extra>
        <el-button :icon="IPixelPlus" type="primary" @click="onNewIteration">新建迭代</el-button>
      </template>
    </el-page-header>

    <div class="body">
      <!-- 左：md-editor + 子需求清单区 -->
      <div class="editor-pane">
        <template v-if="selectedIteration">
          <div class="iter-head">
            <span class="iter-date">📅 {{ formatDate(selectedIteration.date) }}</span>
            <el-select
              v-model="bufferModuleNames"
              size="small"
              multiple
              filterable
              allow-create
              default-first-option
              collapse-tags
              placeholder="所属模块"
              style="width: 220px"
            >
              <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
            </el-select>
            <el-select v-model="bufferFeature" size="small" filterable allow-create placeholder="功能名称" style="width: 160px">
              <el-option v-for="f in featureOptions" :key="f" :label="displayFeatureName(f)" :value="f" />
            </el-select>
            <el-select v-model="bufferStatus" size="small" style="width: 130px">
              <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
            </el-select>
            <el-date-picker
              v-model="bufferDeadline"
              type="date"
              value-format="YYYY-MM-DD"
              clearable
              placeholder="完成时限"
              size="small"
              style="width: 140px"
              :disabled="bufferStatus === 'deferred'"
            />
            <el-button type="primary" size="small" @click="onSave">保存</el-button>
          </div>
          <div class="editor-wrapper">
            <MdEditor
              v-model="bufferContent"
              :key="selectedIteration?.id"
              v-bind="MD_EDITOR_PROPS"
              class="editor"
            />
          </div>
        </template>
        <el-empty v-else description="该功能暂无迭代记录" />
      </div>

      <!-- 右：el-timeline -->
      <div class="timeline-pane">
        <div class="tl-title">迭代时间轴（点击跳转）</div>
        <div class="tl-scroll">
          <el-timeline class="tl">
            <el-timeline-item
              v-for="it in [...currentIterations].reverse()"
              :key="it.id"
              :timestamp="formatDate(it.date)"
              :type="STATUS_TAG_TYPE[it.status] as never"
              placement="top"
            >
              <div
                class="tl-node"
                :class="{ active: it.id === selectedIterationId }"
                @click="onJumpTo(it.id)"
              >
                <span class="tl-content">{{ it.content || '（空）' }}</span>
                <span v-if="it.completion_deadline" class="tl-deadline">
                  🗓 {{ formatDate(it.completion_deadline) }}
                </span>
                <el-tag :type="STATUS_TAG_TYPE[it.status] as never" size="small">
                  {{ STATUS_LABEL[it.status] }}
                </el-tag>
                <el-button
                  :icon="IPixelTrash"
                  link
                  size="small"
                  type="danger"
                  @click.stop="onDeleteIteration(it.id)"
                />
              </div>
            </el-timeline-item>
          </el-timeline>
        </div>
      </div>
    </div>

    <!-- 子需求清单区（迭代级，随 timeline 切换） -->
    <div v-if="selectedIteration" class="subitem-pane">
      <div class="subitem-head">
        <span class="subitem-title">
          📋 子需求清单（当前迭代 · {{ formatDate(selectedIteration.date) }}）
        </span>
        <span v-if="subitemProgressText" class="subitem-progress">{{ subitemProgressText }}</span>
      </div>
      <div class="subitem-list">
        <div v-if="currentSubitems.length === 0" class="subitem-empty">暂无子需求</div>
        <div v-for="s in currentSubitems" :key="s.id" class="subitem-row">
          <span class="subitem-seq">{{ s.seq }}.</span>
          <span class="subitem-content">{{ s.content }}</span>
          <el-select
            :model-value="s.status"
            size="small"
            style="width: 110px"
            @change="(v: RequirementStatus) => onSubitemStatusChange(s.id, v)"
          >
            <el-option v-for="st in statusOptions" :key="st" :label="STATUS_LABEL[st]" :value="st" />
          </el-select>
          <el-date-picker
            :model-value="displayDeadline(s)"
            type="date"
            value-format="YYYY-MM-DD"
            clearable
            size="small"
            placeholder="时限"
            style="width: 130px"
            :disabled="s.status === 'deferred'"
            @update:model-value="(v: string | null) => onSubitemDeadlineChange(s.id, v, s.status)"
          />
          <el-button
            :icon="IPixelTrash"
            link
            size="small"
            type="danger"
            @click="onDeleteSubitem(s.id)"
          />
        </div>
        <!-- 底部新增行：默认只读占位 + 添加按钮；点击进入多行编辑，添加按钮变为确定 -->
        <div v-if="!isAddingSubitem" class="subitem-row subitem-add-row" @click="startAddSubitem">
          <span class="subitem-add-placeholder">＋ 添加子需求…</span>
          <el-button size="small" type="primary">添加</el-button>
        </div>
        <div v-else class="subitem-row subitem-add-row editing">
          <el-input
            ref="addInputRef"
            v-model="newSubitemContent"
            type="textarea"
            :autosize="{ minRows: 1, maxRows: 6 }"
            resize="none"
            placeholder="输入子需求内容（支持多行），Ctrl+Enter 确定"
            @keydown.ctrl.enter.prevent="confirmAddSubitem"
            @keydown.meta.enter.prevent="confirmAddSubitem"
          />
          <el-button size="small" type="primary" @click="confirmAddSubitem">确定</el-button>
          <el-button size="small" @click="cancelAddSubitem">取消</el-button>
        </div>
      </div>
    </div>

    <RequirementEditDialog v-model="editVisible" mode="create" />
  </div>
</template>

<style scoped>
.detail {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.head {
  flex-shrink: 0;
  margin-bottom: 12px;
}
.title {
  font-weight: 600;
  font-size: 15px;
}
.body {
  flex: 1;
  display: flex;
  gap: 16px;
  min-height: 0;
}
.editor-pane {
  flex: 2;
  display: flex;
  flex-direction: column;
  min-width: 0;
  min-height: 0;
}
/* md-editor 外层包裹：撑满编辑区剩余高度，内部编辑器 100% 自适应 */
.editor-wrapper {
  flex: 1;
  min-height: 0;
  overflow: hidden;
}
.editor-wrapper :deep(.md-editor) {
  height: 100%;
}
/* md-editor footer 字数统计垂直居中：见 styles/main.css 全局规则 */
.iter-head {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 10px;
  margin-bottom: 8px;
}
.iter-date {
  color: #d97706;
  font-weight: 500;
}
.timeline-pane {
  flex: 1;
  min-width: 220px;
  max-width: 340px;
  display: flex;
  flex-direction: column;
  min-height: 0;
  border-left: 1px solid #e5e7eb;
  padding-left: 12px;
}
.tl-title {
  flex-shrink: 0;
  font-weight: 600;
  font-size: 13px;
  color: #374151;
  margin-bottom: 10px;
}
.tl-scroll {
  flex: 1;
  min-height: 0;
  overflow: auto;
}
.tl {
  padding: 0 4px;
}
.tl-node {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 8px;
  border-radius: 6px;
  border: 1px solid #e5e7eb;
  background: #ffffff;
  cursor: pointer;
}
.tl-node:hover {
  background: #f3f4f6;
}
.tl-node.active {
  border-color: #409eff;
  background: #ecf5ff;
}
.tl-content {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.tl-deadline {
  flex-shrink: 0;
  font-size: 12px;
  color: #d97706;
  white-space: nowrap;
}
/* 子需求清单区 */
.subitem-pane {
  flex-shrink: 0;
  border-top: 1px solid #e5e7eb;
  margin-top: 12px;
  padding-top: 10px;
  /* 视口一半为上限；无子需求也保持 30vh 最小高度，保证可见性 */
  min-height: 30vh;
  max-height: 50vh;
  display: flex;
  flex-direction: column;
}
.subitem-head {
  display: flex;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
  flex-wrap: wrap;
}
.subitem-title {
  font-weight: 600;
  font-size: 13px;
  color: #374151;
}
.subitem-progress {
  font-size: 12px;
  color: #6b7280;
}
/* 底部新增行：复用 subitem-row 的对齐/分隔，只覆盖行内布局 */
.subitem-add-row {
  cursor: pointer;
  /* 顶部对齐：让 textarea 多行时按钮列与首行基线对齐 */
  align-items: flex-start;
}
/* 编辑态：行本身不可点（仅输入框/按钮响应），避免误触 */
.subitem-add-row.editing {
  cursor: default;
}
/* textarea 占满内容列 */
.subitem-add-row.editing :deep(.el-input) {
  flex: 1;
  min-width: 0;
}
/* 默认占位态：提示文字撑满，添加按钮靠右 */
.subitem-add-placeholder {
  flex: 1;
  font-size: 13px;
  color: #9ca3af;
  padding: 2px 0;
}
.subitem-add-row:hover .subitem-add-placeholder {
  color: #409eff;
}
.subitem-list {
  overflow: auto;
  min-height: 0;
  flex: 1;
}
.subitem-empty {
  font-size: 13px;
  color: #9ca3af;
  padding: 8px 4px;
}
.subitem-row {
  display: flex;
  /* 垂直居中：序号/内容/选择器/日期/删除按钮在行内对齐居中 */
  align-items: center;
  gap: 8px;
  padding: 6px 4px;
  border-bottom: 1px solid #f3f4f6;
}
.subitem-seq {
  flex-shrink: 0;
  color: #9ca3af;
  font-size: 13px;
  width: 24px;
  line-height: 1.6;
}
.subitem-content {
  flex: 1;
  font-size: 13px;
  color: #1f2937;
  /* 完整显示：保留换行 + 长串自动断行，禁止 ... 截断（子需求没有详情入口） */
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.6;
  /* 允许用户选中复制内容 */
  user-select: text;
}
</style>
