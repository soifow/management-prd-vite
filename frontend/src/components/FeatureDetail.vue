<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete } from '@element-plus/icons-vue'
import { MdEditor } from 'md-editor-v3'

import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import type { RequirementStatus } from '@/types'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { formatDate } from '@/utils'
import RequirementEditDialog from '@/components/RequirementEditDialog.vue'

const projectsStore = useProjectsStore()
const store = useRequirementsStore()
const {
  selectedFeature,
  currentIterations,
  selectedIteration,
  selectedIterationId,
  currentSubitems,
  modules,
} = storeToRefs(store)
const { activeProjectId } = storeToRefs(projectsStore)

const editVisible = ref(false)

// 编辑缓冲（避免直接改 store 引用）
const bufferContent = ref('')
const bufferStatus = ref<RequirementStatus>('todo')
const bufferModuleNames = ref<string[]>([])
const bufferFeature = ref('')
/** 完成时限缓冲（null = 无时限） */
const bufferDeadline = ref<string | null>(null)
const featureOptions = ref<string[]>([])

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

// 子需求行内新建
const newSubitemContent = ref('')
async function onAddSubitem() {
  const itId = selectedIterationId.value
  const content = newSubitemContent.value.trim()
  if (!itId || !content) return
  try {
    await store.addSubitem(itId, content, 'todo')
    newSubitemContent.value = ''
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '添加子需求失败')
  }
}

async function onToggleSubitemDone(subitemId: string, current: RequirementStatus) {
  // 勾选 = 切 done；取消 = 切 todo（高频）
  const next: RequirementStatus = current === 'done' ? 'todo' : 'done'
  try {
    await store.setSubitemStatusItem(subitemId, next)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '更新失败')
  }
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
  try {
    await store.patchSubitem(subitemId, {
      completion_deadline: deadline ?? undefined,
      clear_completion_deadline: deadline === null,
      status,
    })
  } catch (e) {
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
    <el-page-header class="head" @back="onBack">
      <template #content>
        <span class="title">功能：{{ selectedFeature.feature || '（未命名）' }}</span>
      </template>
      <template #extra>
        <el-button :icon="Plus" type="primary" @click="onNewIteration">新建迭代</el-button>
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
              <el-option v-for="f in featureOptions" :key="f" :label="f" :value="f" />
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
              :preview="false"
              :code-foldable="false"
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
                  :icon="Delete"
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
        <div class="subitem-add">
          <el-input
            v-model="newSubitemContent"
            size="small"
            placeholder="添加子需求，回车提交"
            style="width: 260px"
            @keyup.enter="onAddSubitem"
          />
          <el-button :icon="Plus" size="small" type="primary" @click="onAddSubitem">添加</el-button>
        </div>
      </div>
      <div class="subitem-list">
        <div v-if="currentSubitems.length === 0" class="subitem-empty">暂无子需求</div>
        <div v-for="s in currentSubitems" :key="s.id" class="subitem-row">
          <el-checkbox
            :model-value="s.status === 'done'"
            @change="onToggleSubitemDone(s.id, s.status)"
          />
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
            :model-value="s.completion_deadline"
            type="date"
            value-format="YYYY-MM-DD"
            clearable
            size="small"
            placeholder="时限"
            style="width: 130px"
            :disabled="s.status === 'deferred'"
            @change="(v: string | null) => onSubitemDeadlineChange(s.id, v, s.status)"
          />
          <el-button
            :icon="Delete"
            link
            size="small"
            type="danger"
            @click="onDeleteSubitem(s.id)"
          />
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
  max-height: 220px;
  display: flex;
  flex-direction: column;
  min-height: 0;
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
.subitem-add {
  margin-left: auto;
  display: flex;
  gap: 8px;
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
}
.subitem-content {
  flex: 1;
  font-size: 13px;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
</style>
