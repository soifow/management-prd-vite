<script setup lang="ts">
import { ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'
import { Plus, Delete, Edit, Upload, FolderAdd } from '@element-plus/icons-vue'

import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import ProjectDialog from '@/components/ProjectDialog.vue'
import ImportPreviewDialog from '@/components/ImportPreviewDialog.vue'
import type { ParsedRequirement } from '@/types'
import { formatYymmdd } from '@/utils'
import { useTemplateRef } from 'vue'

const projectsStore = useProjectsStore()
const requirementsStore = useRequirementsStore()
const { summaries, activeProjectId } = storeToRefs(projectsStore)

const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'rename'>('create')
const dialogInitialName = ref('')

const ImportPreviewDialogRef = useTemplateRef('importDialog')

function openCreate() {
  dialogMode.value = 'create'
  dialogInitialName.value = ''
  dialogVisible.value = true
}

async function onDelete(id: string) {
  const summary = summaries.value.find((s) => s.id === id)
  const name = summary?.name ?? ''
  const count = summary?.requirement_count ?? 0
  try {
    await ElMessageBox.confirm(
      `确定删除项目「${name}」吗？将级联删除其 ${count} 条需求，且无法恢复。`,
      '删除项目',
      { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
    )
    await projectsStore.remove(id)
    ElMessage.success('项目已删除')
  } catch (e) {
    if (e !== 'cancel') {
      ElMessage.error(e instanceof Error ? e.message : '删除失败')
    }
  }
}

function onRename(id: string) {
  const summary = summaries.value.find((s) => s.id === id)
  dialogMode.value = 'rename'
  dialogInitialName.value = summary?.name ?? ''
  dialogVisible.value = true
}

function selectProject(id: string) {
  projectsStore.select(id)
}

// 导入到当前项目：需先选中项目
async function onImportCurrent() {
  if (!activeProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  try {
    const parsed = await requirementsStore.pickAndImport()
    if (!parsed) return
    ImportPreviewDialogRef.value?.open(parsed.requirements, 'current')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入解析失败')
  }
}

// 导入为新建项目：不要求已有项目，项目名从文件名推测
async function onImportAsNew() {
  try {
    const parsed = await requirementsStore.pickAndImport()
    if (!parsed) return
    ImportPreviewDialogRef.value?.open(parsed.requirements, 'new', parsed.filename)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入解析失败')
  }
}
</script>

<template>
  <div class="sidebar">
    <div class="header">
      <span class="title">项目</span>
    </div>

    <div class="actions">
      <el-button :icon="Plus" plain size="small" class="action-btn" @click="openCreate">
        新建项目
      </el-button>
      <el-button
        :icon="FolderAdd"
        plain
        size="small"
        class="action-btn"
        @click="onImportAsNew"
      >
        导入新建项目
      </el-button>
      <el-button
        :icon="Upload"
        plain
        size="small"
        class="action-btn"
        :disabled="!activeProjectId"
        @click="onImportCurrent"
      >
        导入当前项目
      </el-button>
    </div>

    <div class="list">
      <div
        v-for="p in summaries"
        :key="p.id"
        class="item"
        :class="{ active: p.id === activeProjectId }"
        @click="selectProject(p.id)"
      >
        <div class="item-top">
          <span class="name" :title="p.name">{{ p.name }}</span>
          <span class="ops">
            <el-icon @click.stop="onRename(p.id)"><Edit /></el-icon>
            <el-icon @click.stop="onDelete(p.id)"><Delete /></el-icon>
          </span>
        </div>
        <div class="item-meta">
          <span>{{ p.requirement_count }} 条需求</span>
          <span v-if="p.latest_done_or_ui_date" class="date-tag">
            最新 {{ formatYymmdd(p.latest_done_or_ui_date) }}
          </span>
        </div>
      </div>
      <div v-if="summaries.length === 0" class="empty">暂无项目，请新建</div>
    </div>

    <ProjectDialog
      v-model="dialogVisible"
      :mode="dialogMode"
      :initial-name="dialogInitialName"
      :project-id="dialogMode === 'rename' ? activeProjectId ?? '' : ''"
    />
    <ImportPreviewDialog ref="importDialog" />
  </div>
</template>

<style scoped>
.sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
}
.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 16px 16px 8px;
}
.title {
  font-weight: 600;
  font-size: 15px;
}
.actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 16px 12px;
}
.action-btn {
  width: 100%;
  /* 三个按钮左对齐，图标与文字起点统一（覆盖 el-button 默认居中） */
  justify-content: flex-start;
}
.list {
  flex: 1;
  overflow: auto;
  padding: 0 8px;
}
.item {
  padding: 10px 12px;
  border-radius: 6px;
  cursor: pointer;
  margin-bottom: 4px;
}
.item:hover {
  background: #f3f4f6;
}
.item.active {
  background: #ecf5ff;
  /* 左侧蓝色竖线明确标识当前项目（不影响布局） */
  box-shadow: inset 3px 0 0 0 #409eff;
}
.item-top {
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.name {
  font-size: 14px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.ops {
  display: none;
  gap: 6px;
  color: #6b7280;
}
.item:hover .ops {
  display: flex;
}
.ops .el-icon:hover {
  color: #dc2626;
}
.item-meta {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
  display: flex;
  justify-content: space-between;
}
.date-tag {
  color: #d97706;
  font-weight: 500;
}
.empty {
  text-align: center;
  color: #9ca3af;
  padding: 24px 0;
  font-size: 13px;
}
</style>
