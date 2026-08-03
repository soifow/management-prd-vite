<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useProjectsStore } from '@/stores/projects'
import { useBugsStore } from '@/stores/bugs'
import { IPixelPencil, IPixelPlus, IPixelTrash } from '@/constants/icons'
import ProjectDialog from '@/components/ProjectDialog.vue'
import type { ViewMode } from '@/types'
import { formatDate } from '@/utils'
import { ref } from 'vue'

const projectsStore = useProjectsStore()
const bugsStore = useBugsStore()
const { summaries, activeProjectId } = storeToRefs(projectsStore)
const { viewMode } = storeToRefs(bugsStore)

// 聚合方式切换：active=按时间，inactive=按模块（与 ProjectSidebar 同款）
function onViewModeChange(val: string | number | boolean) {
  viewMode.value = val as ViewMode
}

// 新建 / 重命名 / 删除项目：bug 视图与工作区共享同一份 projects 表与
// useProjectsStore.summaries，任一侧新建都会响应式同步到另一侧列表
const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'rename'>('rename')
const dialogInitialName = ref('')
const renameId = ref('')

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
      `确定删除项目「${name}」吗？将级联删除其 ${count} 条需求与全部 bug，且无法恢复。`,
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
  renameId.value = id
  dialogMode.value = 'rename'
  dialogInitialName.value = summary?.name ?? ''
  dialogVisible.value = true
}

function selectProject(id: string) {
  projectsStore.select(id)
}
</script>

<template>
  <div class="sidebar">
    <div class="header">
      <span class="title">项目</span>
      <el-switch
        :model-value="viewMode"
        size="small"
        active-value="date"
        inactive-value="module"
        active-text="时间"
        inactive-text="模块"
        @change="onViewModeChange"
      />
    </div>

    <div class="actions">
      <el-button plain size="small" class="action-btn" @click="openCreate">
        <el-icon class="action-icon"><IPixelPlus /></el-icon>
        <span>新建项目</span>
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
            <el-icon @click.stop="onRename(p.id)"><IPixelPencil /></el-icon>
            <el-icon @click.stop="onDelete(p.id)"><IPixelTrash /></el-icon>
          </span>
        </div>
        <div v-if="p.list_date" class="item-meta">
          <span class="date-tag">最新 {{ formatDate(p.list_date) }}</span>
        </div>
      </div>
      <div v-if="summaries.length === 0" class="empty">暂无项目，请新建</div>
    </div>

    <ProjectDialog
      v-model="dialogVisible"
      :mode="dialogMode"
      :initial-name="dialogInitialName"
      :project-id="dialogMode === 'rename' ? renameId : ''"
    />
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
  gap: 8px;
}
.title {
  font-weight: 600;
  font-size: 15px;
  flex-shrink: 0;
}
.actions {
  display: flex;
  flex-direction: column;
  gap: 8px;
  padding: 4px 16px 12px;
}
.action-btn {
  width: 100%;
  /* 左对齐，图标与文字起点统一（覆盖 el-button 默认居中） */
  justify-content: flex-start;
  gap: 6px;
}
.action-icon {
  width: 14px;
  height: 14px;
  flex-shrink: 0;
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
