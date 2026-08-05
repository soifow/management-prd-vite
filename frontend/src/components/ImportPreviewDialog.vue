<script setup lang="ts">
import { computed, ref } from 'vue'

import { useRequirementsStore } from '@/stores/requirements'
import type { ImportTarget, ParsedProject } from '@/types'
import ImportPreviewPanel from '@/components/ImportPreviewPanel.vue'

const store = useRequirementsStore()
const visible = ref(false)
const parsed = ref<ParsedProject | null>(null)

// 导入模式：current=导入当前项目；new=新建项目并导入（smart 由 SmartImportDialog 承载）
const mode = ref<'current' | 'new'>('current')
const projectName = ref('')

const dialogTitle = computed(() => (mode.value === 'new' ? '导入新建项目' : '导入当前项目'))
const applyLabel = computed(() => (mode.value === 'new' ? '新建并导入' : '应用导入'))

// target 由 mode 决定：current -> 当前项目 id；new -> 新建（name 由 panel 编辑）
const target = computed<ImportTarget>(() => {
  if (mode.value === 'new') return { name: '' }
  return { project_id: store.project?.id ?? '' }
})

function open(p: ParsedProject, m: 'current' | 'new' = 'current', filename = '') {
  parsed.value = structuredClone(p)
  mode.value = m
  projectName.value = filename || p.name
  visible.value = true
}

defineExpose({ open })

function onApplySuccess() {
  visible.value = false
}
</script>

<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="960px" top="5vh">
    <ImportPreviewPanel
      v-if="parsed"
      :parsed="parsed"
      :target="target"
      :reuse-id="true"
      :apply-label="applyLabel"
      v-model:project-name="projectName"
      @apply-success="onApplySuccess"
    />
  </el-dialog>
</template>
