<script setup lang="ts">
import { ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'

import { useProjectsStore } from '@/stores/projects'

const props = defineProps<{
  modelValue: boolean
  mode: 'create' | 'rename'
  initialName: string
  projectId: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const projectsStore = useProjectsStore()
const { activeProjectId } = storeToRefs(projectsStore)

const nameInput = ref('')

watch(
  () => props.modelValue,
  (visible) => {
    if (visible) nameInput.value = props.initialName
  },
)

async function onSubmit() {
  if (!nameInput.value.trim()) {
    ElMessage.warning('项目名不能为空')
    return
  }
  try {
    if (props.mode === 'create') {
      await projectsStore.create(nameInput.value)
      ElMessage.success('项目已创建')
    } else {
      const id = props.projectId || activeProjectId.value || ''
      if (!id) {
        ElMessage.error('未选择项目')
        return
      }
      await projectsStore.rename(id, nameInput.value)
      ElMessage.success('项目已重命名')
    }
    emit('update:modelValue', false)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '操作失败')
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="mode === 'create' ? '新建项目' : '重命名项目'"
    width="420px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-input v-model="nameInput" placeholder="项目名" />
    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="onSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>
