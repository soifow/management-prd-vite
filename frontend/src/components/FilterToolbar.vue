<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'

import { useRequirementsStore } from '@/stores/requirements'
import type { RequirementStatus } from '@/types'
import { STATUS_LABEL } from '@/types/requirement'
import RequirementEditDialog from '@/components/RequirementEditDialog.vue'
import ExportDialog from '@/components/ExportDialog.vue'
import { IPixelDownload, IPixelPlus } from '@/constants/icons'
import { ref } from 'vue'

const store = useRequirementsStore()
const { filters, project } = storeToRefs(store)

const editVisible = ref(false)
const exportDialogRef = ref<InstanceType<typeof ExportDialog> | null>(null)

const statusOptions: { value: RequirementStatus; label: string }[] = [
  { value: 'todo', label: STATUS_LABEL.todo },
  { value: 'ui_done_waiting_backend', label: STATUS_LABEL.ui_done_waiting_backend },
  { value: 'done', label: STATUS_LABEL.done },
  { value: 'deferred', label: STATUS_LABEL.deferred },
]

// 日期范围：桥接 filters.dateFrom / dateTo ↔ daterange 选择器
const dateRange = computed<[string, string] | null>({
  get() {
    return filters.value.dateFrom && filters.value.dateTo
      ? [filters.value.dateFrom, filters.value.dateTo]
      : null
  },
  set(val) {
    if (val) {
      filters.value.dateFrom = val[0]
      filters.value.dateTo = val[1]
    } else {
      filters.value.dateFrom = ''
      filters.value.dateTo = ''
    }
  },
})

function openCreate() {
  if (!project.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  editVisible.value = true
}

async function onExport() {
  if (!project.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  exportDialogRef.value?.open()
}
</script>

<template>
  <div class="toolbar">
    <el-date-picker
      v-model="dateRange"
      type="daterange"
      range-separator="~"
      start-placeholder="开始日期"
      end-placeholder="结束日期"
      value-format="YYYY-MM-DD"
      style="width: 160px; --el-date-editor-daterange-width: 160px"
    />
    <el-select
      v-model="filters.statuses"
      multiple
      collapse-tags
      collapse-tags-tooltip
      placeholder="状态筛选"
      style="width: 150px"
    >
      <el-option
        v-for="opt in statusOptions"
        :key="opt.value"
        :label="opt.label"
        :value="opt.value"
      />
    </el-select>
    <el-input
      v-model="filters.keyword"
      placeholder="关键字（功能/内容/模块）"
      clearable
      style="width: 220px"
    />

    <div class="spacer" />

    <el-button :icon="IPixelDownload" @click="onExport" :disabled="!project">导出</el-button>
    <el-button :icon="IPixelPlus" type="primary" @click="openCreate" :disabled="!project">
      需求
    </el-button>

    <RequirementEditDialog v-model="editVisible" mode="create" />
    <ExportDialog ref="exportDialogRef" />
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.spacer {
  flex: 1;
}
</style>
