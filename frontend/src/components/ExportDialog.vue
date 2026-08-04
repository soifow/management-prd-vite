<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { ElMessage } from 'element-plus'

import { exportProjectMd } from '@/api'
import { useRequirementsStore } from '@/stores/requirements'

const store = useRequirementsStore()
const project = computed(() => store.project)
const visible = ref(false)
const includeBug = ref(true)

// 动态丢失提示：取消勾选时显示将丢失的 bug 数量与关联数。
// bugs 不在 requirements store 内，弹窗打开时拉取一次计数。
const projectBugCount = ref(0)
const projectLinkCount = ref(0)

watch(visible, async (v) => {
  if (v && project.value) {
    // 拉取该项目 bug 用于统计
    try {
      const bugs = await window.pywebview?.api.list_bugs(project.value.id)
      if (Array.isArray(bugs)) {
        projectBugCount.value = bugs.length
        const links = bugs.filter(
          (b: { linked_iteration_id: string | null }) => b.linked_iteration_id,
        ).length
        projectLinkCount.value = links
      }
    } catch {
      // 拉取失败不影响主流程
      projectBugCount.value = 0
      projectLinkCount.value = 0
    }
  }
})

function open() {
  includeBug.value = true
  visible.value = true
}

defineExpose({ open })

async function onConfirm() {
  if (!project.value) return
  try {
    const path = await exportProjectMd(project.value.id, includeBug.value)
    if (path) {
      ElMessage.success(`已导出：${path}`)
      visible.value = false
    }
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导出失败')
  }
}
</script>

<template>
  <el-dialog v-model="visible" title="导出项目" width="480px">
    <div v-if="project" class="form">
      <div class="row">
        <span class="label">项目名：</span>
        <el-input :model-value="project.name" readonly style="width: 280px" />
      </div>

      <div class="row">
        <el-checkbox v-model="includeBug">包含 Bug 数据</el-checkbox>
      </div>

      <div v-if="!includeBug && projectBugCount > 0" class="loss-warning">
        ⚠ 取消勾选将丢失：{{ projectBugCount }} 条 bug
        <span v-if="projectLinkCount > 0">，{{ projectLinkCount }} 个需求关联</span>
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onConfirm">导出</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.form {
  display: flex;
  flex-direction: column;
  gap: 14px;
}
.row {
  display: flex;
  align-items: center;
  gap: 10px;
}
.label {
  font-size: 13px;
  color: #374151;
  flex-shrink: 0;
}
.loss-warning {
  font-size: 12px;
  color: #dc2626;
  background: #fef2f2;
  border: 1px solid #fecaca;
  border-radius: 4px;
  padding: 6px 10px;
}
</style>
