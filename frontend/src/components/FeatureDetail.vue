<script setup lang="ts">
import { ref, watch } from 'vue'
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
const { selectedFeature, currentIterations, selectedIteration, selectedIterationId, modules } =
  storeToRefs(store)
const { activeProjectId } = storeToRefs(projectsStore)

const editVisible = ref(false)

// 编辑缓冲（避免直接改 store 引用）
const bufferContent = ref('')
const bufferStatus = ref<RequirementStatus>('todo')
const bufferModule = ref('')
const bufferFeature = ref('')
/** 完成时限缓冲（null = 无时限） */
const bufferDeadline = ref<string | null>(null)
const featureOptions = ref<string[]>([])

// 按当前模块拉取已有功能名候选（沿用编辑弹窗逻辑）
async function refreshFeatureOptions() {
  if (!activeProjectId.value) {
    featureOptions.value = []
    return
  }
  featureOptions.value = await store.listFeatures(activeProjectId.value, bufferModule.value)
}

watch(selectedIteration, (it) => {
  if (it) {
    bufferContent.value = it.content
    bufferStatus.value = it.status
    bufferModule.value = it.module
    bufferFeature.value = it.feature
    bufferDeadline.value = it.completion_deadline
    void refreshFeatureOptions()
  }
})

// 模块切换时刷新功能候选（当前输入的功能名保留，不强制清空）
watch(bufferModule, () => {
  void refreshFeatureOptions()
})

// 暂缓状态联动清空时限（前端即时反馈；后端亦强制）
watch(bufferStatus, (s) => {
  if (s === 'deferred') bufferDeadline.value = null
})

// el-autocomplete 建议回调：v-model 即输入框值，失焦天然保留
function querySearchModule(query: string, cb: (results: { value: string }[]) => void) {
  const q = query.trim().toLowerCase()
  const list = modules.value
    .filter((m) => m.toLowerCase().includes(q))
    .map((m) => ({ value: m }))
  cb(list)
}

function querySearchFeature(query: string, cb: (results: { value: string }[]) => void) {
  const q = query.trim().toLowerCase()
  const list = featureOptions.value
    .filter((f) => f.toLowerCase().includes(q))
    .map((f) => ({ value: f }))
  cb(list)
}

const statusOptions: RequirementStatus[] = [
  'todo',
  'ui_done_waiting_backend',
  'done',
  'deferred',
]

async function onSave() {
  if (!selectedIteration.value) return
  try {
    await store.updateIteration(selectedIteration.value.id, {
      module: bufferModule.value,
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
  store.selectIteration(id)
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
</script>

<template>
  <div v-if="selectedFeature" class="detail">
    <el-page-header class="head" @back="onBack">
      <template #content>
        <span class="title">功能：{{ selectedFeature.feature || '（未命名）' }}</span>
        <span v-if="selectedFeature.module" class="module">（{{ selectedFeature.module }}）</span>
      </template>
      <template #extra>
        <el-button :icon="Plus" type="primary" @click="onNewIteration">新建迭代</el-button>
      </template>
    </el-page-header>

    <div class="body">
      <!-- 左：md-editor -->
      <div class="editor-pane">
        <template v-if="selectedIteration">
          <div class="iter-head">
            <span class="iter-date">📅 {{ formatDate(selectedIteration.date) }}</span>
            <el-autocomplete
              v-model="bufferModule"
              :fetch-suggestions="querySearchModule"
              size="small"
              clearable
              :trigger-on-focus="true"
              placeholder="所属模块"
              style="width: 140px"
            />
            <el-autocomplete
              v-model="bufferFeature"
              :fetch-suggestions="querySearchFeature"
              size="small"
              clearable
              :trigger-on-focus="true"
              placeholder="功能名称"
              style="width: 160px"
            />
            <el-select v-model="bufferStatus" size="small" style="width: 160px">
              <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
            </el-select>
            <el-date-picker
              v-model="bufferDeadline"
              type="date"
              value-format="YYYY-MM-DD"
              clearable
              placeholder="完成时限"
              size="small"
              style="width: 150px"
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
.module {
  color: #6b7280;
  font-weight: 400;
  font-size: 13px;
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
/* md-editor footer 字数统计垂直居中 */
.editor-wrapper :deep(.md-editor-footer-item) {
  align-items: center;
}
.editor-wrapper :deep(.md-editor-footer-item label),
.editor-wrapper :deep(.md-editor-footer-item span) {
  line-height: 24px;
}
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
</style>
