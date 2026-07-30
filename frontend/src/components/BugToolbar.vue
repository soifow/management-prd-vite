<script setup lang="ts">
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { Plus } from '@element-plus/icons-vue'
import { ref } from 'vue'

import { useProjectsStore } from '@/stores/projects'
import { useBugsStore } from '@/stores/bugs'
import BugEditDialog from '@/components/BugEditDialog.vue'
import { LEVEL_LABEL } from '@/types/bug'
import type { BugLevel } from '@/types'

const projectsStore = useProjectsStore()
const bugsStore = useBugsStore()
const { activeProjectId } = storeToRefs(projectsStore)
const { filters, modules } = storeToRefs(bugsStore)

const editVisible = ref(false)

const levelOptions: { value: BugLevel; label: string }[] = (
  Object.keys(LEVEL_LABEL) as BugLevel[]
).map((k) => ({ value: k, label: LEVEL_LABEL[k] }))

function openCreate() {
  if (!activeProjectId.value) {
    ElMessage.warning('请先选择项目')
    return
  }
  if (modules.value.length === 0) {
    ElMessage.warning('该项目暂无模块（需求中未定义模块），无法创建 bug')
    return
  }
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
    <el-input
      v-model="filters.keyword"
      placeholder="关键字（模块/内容）"
      clearable
      style="width: 220px"
    />

    <div class="spacer" />

    <el-button :icon="Plus" type="primary" @click="openCreate" :disabled="!activeProjectId">
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
