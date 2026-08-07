<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { ref } from 'vue'

import { useProjectsStore } from '@/stores/projects'
import { useBugsStore } from '@/stores/bugs'
import BugEditDialog from '@/components/BugEditDialog.vue'
import { LEVEL_LABEL, BUG_STATUS_LABEL } from '@/types/bug'
import { IPixelPlus } from '@/constants/icons'
import type { BugLevel, BugStatus } from '@/types'

const projectsStore = useProjectsStore()
const bugsStore = useBugsStore()
const { activeProjectId } = storeToRefs(projectsStore)
const { filters } = storeToRefs(bugsStore)

const editVisible = ref(false)

const levelOptions: { value: BugLevel; label: string }[] = (
  Object.keys(LEVEL_LABEL) as BugLevel[]
).map((k) => ({ value: k, label: LEVEL_LABEL[k] }))

const statusOptions: { value: BugStatus; label: string }[] = (
  Object.keys(BUG_STATUS_LABEL) as BugStatus[]
).map((k) => ({ value: k, label: BUG_STATUS_LABEL[k] }))

function openCreate() {
  if (!activeProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  // 无模块不再拦截：BugEditDialog 模块控件为 allow-create，可手动输入模块名；
  // 后端 create_bug 的 ensure_modules 会按名自动建模块（见「需求与 Bug 项目独立」方案）。
  editVisible.value = true
}
</script>

<template>
  <div class="toolbar">
    <el-select
      v-model="filters.levels"
      multiple
      collapse-tags
      collapse-tags-tooltip
      placeholder="级别筛选"
      style="width: 150px"
    >
      <el-option v-for="opt in levelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
    </el-select>
    <el-select
      v-model="filters.statuses"
      multiple
      collapse-tags
      collapse-tags-tooltip
      placeholder="状态筛选"
      style="width: 150px"
    >
      <el-option v-for="opt in statusOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
    </el-select>
    <el-input
      v-model="filters.keyword"
      placeholder="关键字（模块/内容）"
      clearable
      style="width: 220px"
    />

    <div class="spacer" />

    <el-button :icon="IPixelPlus" type="primary" @click="openCreate" :disabled="!activeProjectId">
      bug
    </el-button>

    <BugEditDialog v-model="editVisible" mode="create" />
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
