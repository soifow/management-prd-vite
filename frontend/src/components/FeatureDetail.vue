<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Back, Plus, Delete } from '@element-plus/icons-vue'
import { MdEditor } from 'md-editor-v3'

import { useRequirementsStore } from '@/stores/requirements'
import type { RequirementStatus } from '@/types'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { formatYymmdd } from '@/utils'
import RequirementEditDialog from '@/components/RequirementEditDialog.vue'

const store = useRequirementsStore()
const { selectedFeature, currentIterations, selectedIteration, selectedIterationId } =
  storeToRefs(store)

const editVisible = ref(false)

// 编辑缓冲（避免直接改 store 引用）
const bufferContent = ref('')
const bufferStatus = ref<RequirementStatus>('todo')

watch(selectedIteration, (it) => {
  if (it) {
    bufferContent.value = it.content
    bufferStatus.value = it.status
  }
})

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
      content: bufferContent.value,
      status: bufferStatus.value,
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
    <div class="head">
      <el-button :icon="Back" @click="onBack">返回</el-button>
      <span class="title">
        功能：{{ selectedFeature.feature || '（未命名）' }}
        <span v-if="selectedFeature.module" class="module">（{{ selectedFeature.module }}）</span>
      </span>
      <span class="spacer" />
      <el-button :icon="Plus" type="primary" @click="onNewIteration">新建迭代</el-button>
    </div>

    <div class="body">
      <!-- 左：md-editor -->
      <div class="editor-pane">
        <div v-if="selectedIteration" class="iter-head">
          <span class="iter-date">📅 {{ formatYymmdd(selectedIteration.date) }}</span>
          <el-select v-model="bufferStatus" size="small" style="width: 160px">
            <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
          </el-select>
          <el-button type="primary" size="small" @click="onSave">保存</el-button>
        </div>
        <MdEditor
          v-if="selectedIteration"
          v-model="bufferContent"
          :preview="false"
          style="height: calc(100% - 48px)"
        />
        <el-empty v-else description="该功能暂无迭代记录" />
      </div>

      <!-- 右：el-timeline -->
      <div class="timeline-pane">
        <div class="tl-title">迭代时间轴（点击跳转）</div>
        <el-timeline class="tl">
          <el-timeline-item
            v-for="it in [...currentIterations].reverse()"
            :key="it.id"
            :timestamp="formatYymmdd(it.date)"
            :type="STATUS_TAG_TYPE[it.status] as never"
            placement="top"
          >
            <div
              class="tl-node"
              :class="{ active: it.id === selectedIterationId }"
              @click="onJumpTo(it.id)"
            >
              <span class="tl-content">{{ it.content || '（空）' }}</span>
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
  display: flex;
  align-items: center;
  gap: 12px;
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
.spacer {
  flex: 1;
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
}
.iter-head {
  display: flex;
  align-items: center;
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
  border-left: 1px solid #e5e7eb;
  padding-left: 12px;
  overflow: auto;
}
.tl-title {
  font-weight: 600;
  font-size: 13px;
  color: #374151;
  margin-bottom: 10px;
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
</style>
