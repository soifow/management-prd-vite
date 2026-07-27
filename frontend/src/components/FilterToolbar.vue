<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { Download, Plus } from '@element-plus/icons-vue'

import { useRequirementsStore } from '@/stores/requirements'
import type { RequirementStatus } from '@/types'
import { STATUS_LABEL } from '@/types/requirement'
import RequirementEditDialog from '@/components/RequirementEditDialog.vue'
import { ref } from 'vue'

const store = useRequirementsStore()
const { filters, project } = storeToRefs(store)

const editVisible = ref(false)

const statusOptions: { value: RequirementStatus; label: string }[] = [
  { value: 'todo', label: STATUS_LABEL.todo },
  { value: 'ui_done_waiting_backend', label: STATUS_LABEL.ui_done_waiting_backend },
  { value: 'done', label: STATUS_LABEL.done },
  { value: 'deferred', label: STATUS_LABEL.deferred },
]

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
  try {
    const path = await store.exportCurrent()
    if (path) ElMessage.success(`已导出：${path}`)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}
</script>

<template>
  <div class="toolbar">
    <el-date-picker
      v-model="filters.dateFrom"
      type="date"
      placeholder="开始日期"
      value-format="YYYY-MM-DD"
      style="width: 140px"
    />
    <span class="sep">~</span>
    <el-date-picker
      v-model="filters.dateTo"
      type="date"
      placeholder="结束日期"
      value-format="YYYY-MM-DD"
      style="width: 140px"
    />
    <el-select
      v-model="filters.statuses"
      multiple
      collapse-tags
      collapse-tags-tooltip
      placeholder="状态筛选"
      style="width: 200px"
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
      placeholder="关键字（模块/功能/内容）"
      clearable
      style="width: 220px"
    />

    <div class="spacer" />

    <el-button :icon="Download" @click="onExport" :disabled="!project">导出</el-button>
    <el-button :icon="Plus" type="primary" @click="openCreate" :disabled="!project">
      新建需求
    </el-button>

    <RequirementEditDialog v-model="editVisible" mode="create" />
  </div>
</template>

<style scoped>
.toolbar {
  display: flex;
  align-items: center;
  gap: 10px;
  flex-wrap: wrap;
}
.sep {
  color: #9ca3af;
}
.spacer {
  flex: 1;
}
</style>
