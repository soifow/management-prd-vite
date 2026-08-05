<script setup lang="ts">
import { computed, ref } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage, ElMessageBox } from 'element-plus'

import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import { useSettingsStore } from '@/stores/settings'
import {
  IPixelDownload,
  IPixelFolderPlus,
  IPixelPencil,
  IPixelPlus,
  IPixelSparkles,
  IPixelTrash,
} from '@/constants/icons'
import ProjectDialog from '@/components/ProjectDialog.vue'
import ImportPreviewDialog from '@/components/ImportPreviewDialog.vue'
import SmartImportDialog from '@/components/SmartImportDialog.vue'
import type { ViewMode } from '@/types'
import { formatDate } from '@/utils'
import { useTemplateRef } from 'vue'

const projectsStore = useProjectsStore()
const requirementsStore = useRequirementsStore()
const settingsStore = useSettingsStore()
const { summaries, activeProjectId } = storeToRefs(projectsStore)
const { viewMode, smartImporting } = storeToRefs(requirementsStore)

// 智能导入就绪：启用开关 + API 地址 / 密钥 / 模型 齐全
const llmReady = computed(
  () =>
    settingsStore.llmEnabled &&
    !!settingsStore.llmBaseUrl &&
    !!settingsStore.llmApiKey &&
    !!settingsStore.llmModel,
)
const smartImportTooltip = computed(() =>
  llmReady.value
    ? '用 LLM 把任意需求文档/文本识结构化为新项目'
    : '未配置智能导入，请先在「设置 → 智能导入」中开启并填写 API 地址/密钥/模型',
)

// el-switch 切换聚合视图：active=按时间，inactive=按模块
function onViewModeChange(val: string | number | boolean) {
  viewMode.value = val as ViewMode
}

const dialogVisible = ref(false)
const dialogMode = ref<'create' | 'rename'>('create')
const dialogInitialName = ref('')

const ImportPreviewDialogRef = useTemplateRef('importDialog')
const SmartImportDialogRef = useTemplateRef('smartImportDialog')

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
    const result = await requirementsStore.parseImport()
    if (!result) return
    ImportPreviewDialogRef.value?.open(result.parsed, 'current')
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入解析失败')
  }
}

// 导入为新建项目：不要求已有项目，项目名从文件名推测
async function onImportAsNew() {
  try {
    const result = await requirementsStore.parseImport()
    if (!result) return
    ImportPreviewDialogRef.value?.open(result.parsed, 'new', result.filename)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入解析失败')
  }
}

// 智能导入：开三步弹窗（①选择文件 → ②AI 分析 → ③预览并应用）
async function onSmartImport() {
  if (!llmReady.value) {
    ElMessage.warning('请先在「设置 → 智能导入」中开启并配置 LLM')
    return
  }
  SmartImportDialogRef.value?.open()
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
      <el-button plain size="small" class="action-btn" @click="onImportAsNew">
        <el-icon class="action-icon"><IPixelFolderPlus /></el-icon>
        <span>导入新建项目</span>
      </el-button>
      <el-button
        plain
        size="small"
        class="action-btn"
        :disabled="!activeProjectId"
        @click="onImportCurrent"
      >
        <el-icon class="action-icon"><IPixelDownload /></el-icon>
        <span>导入当前项目</span>
      </el-button>
      <el-tooltip :content="smartImportTooltip" placement="right" :show-after="400">
        <span class="tooltip-wrap">
          <el-button
            plain
            size="small"
            class="action-btn"
            :disabled="!llmReady"
            :loading="smartImporting"
            @click="onSmartImport"
          >
            <el-icon class="action-icon"><IPixelSparkles /></el-icon>
            <span>智能导入</span>
          </el-button>
        </span>
      </el-tooltip>
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
        <div class="item-meta">
          <span>{{ p.requirement_count }} 条需求</span>
          <span v-if="p.list_date" class="date-tag">
            最新 {{ formatDate(p.list_date) }}
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
    <SmartImportDialog ref="smartImportDialog" />
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
  /* 三个按钮左对齐，图标与文字起点统一（覆盖 el-button 默认居中） */
  justify-content: flex-start;
  gap: 6px;
}
/* 覆盖 element-plus 默认 .el-button+.el-button{margin-left:12px}：
   该规则本为横向按钮组设计间距，纵向排列时会让第 2、3 个按钮整体右移 12px */
.actions :deep(.el-button + .el-button) {
  margin-left: 0;
}
.action-icon {
  /* 固定图标尺寸，消除不同图标内部留白差异导致的视觉错位 */
  width: 14px;
  height: 14px;
  flex-shrink: 0;
}
.tooltip-wrap {
  /* 禁用按钮不触发鼠标事件，故用块级 span 承接 hover 以显示 tooltip */
  display: block;
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
