<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { MdEditor } from 'md-editor-v3'

import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import type { RequirementStatus } from '@/types'
import { STATUS_LABEL } from '@/types/requirement'
import { isoDate } from '@/utils'

const props = defineProps<{
  modelValue: boolean
  mode: 'create' | 'edit'
  itemId?: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const projectsStore = useProjectsStore()
const requirementsStore = useRequirementsStore()
const { activeProjectId } = storeToRefs(projectsStore)
const { modules, selectedFeature } = storeToRefs(requirementsStore)

const moduleInput = ref('')
const featureInput = ref('')
const contentInput = ref('')
const statusInput = ref<RequirementStatus>('todo')
const dateInput = ref(isoDate(new Date()))
const featureOptions = ref<string[]>([])

const editingItem = computed(() => {
  if (props.mode !== 'edit' || !props.itemId) return null
  return requirementsStore.currentIterations.find((it) => it.id === props.itemId) ?? null
})

async function refreshFeatureOptions() {
  if (!activeProjectId.value) {
    featureOptions.value = []
    return
  }
  featureOptions.value = await requirementsStore.listFeatures(activeProjectId.value, moduleInput.value)
}

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) return
    if (props.mode === 'edit' && editingItem.value) {
      moduleInput.value = editingItem.value.module
      featureInput.value = editingItem.value.feature
      contentInput.value = editingItem.value.content
      statusInput.value = editingItem.value.status
      dateInput.value = editingItem.value.date
    } else {
      // 新建：预填当前功能的 module/feature
      moduleInput.value = selectedFeature.value?.module ?? ''
      featureInput.value = selectedFeature.value?.feature ?? ''
      contentInput.value = ''
      statusInput.value = 'todo'
      dateInput.value = isoDate(new Date())
    }
    await refreshFeatureOptions()
  },
)

watch(moduleInput, () => {
  if (props.modelValue) refreshFeatureOptions()
})

const statusOptions: RequirementStatus[] = [
  'todo',
  'ui_done_waiting_backend',
  'done',
  'deferred',
]

async function onSubmit() {
  if (!activeProjectId.value) {
    ElMessage.warning('未选择项目')
    return
  }
  if (!contentInput.value.trim()) {
    ElMessage.warning('需求内容不能为空')
    return
  }
  if (!dateInput.value) {
    ElMessage.warning('请选择日期')
    return
  }

  try {
    if (props.mode === 'create') {
      await requirementsStore.createIteration({
        module: moduleInput.value,
        feature: featureInput.value || contentInput.value.trim(),
        content: contentInput.value,
        status: statusInput.value,
        date: dateInput.value,
      })
      ElMessage.success('已新建迭代')
    } else if (editingItem.value) {
      await requirementsStore.updateIteration(editingItem.value.id, {
        module: moduleInput.value,
        feature: featureInput.value,
        content: contentInput.value,
        status: statusInput.value,
        date: dateInput.value,
      })
      ElMessage.success('已更新')
    }
    emit('update:modelValue', false)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="mode === 'create' ? '新建迭代' : '编辑迭代'"
    width="720px"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-form label-width="80px">
      <el-form-item label="模块">
        <el-select
          v-model="moduleInput"
          filterable
          allow-create
          default-first-option
          placeholder="选择已有模块或输入新模块"
          style="width: 100%"
        >
          <el-option label="（未分组）" value="" />
          <el-option v-for="m in modules" :key="m" :label="m" :value="m" />
        </el-select>
      </el-form-item>
      <el-form-item label="功能名">
        <el-select
          v-model="featureInput"
          filterable
          allow-create
          default-first-option
          placeholder="选择已有功能或输入新功能（同名功能聚合为迭代）"
          style="width: 100%"
        >
          <el-option v-for="f in featureOptions" :key="f" :label="f" :value="f" />
        </el-select>
      </el-form-item>
      <el-form-item label="状态">
        <el-select v-model="statusInput" style="width: 100%">
          <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
        </el-select>
      </el-form-item>
      <el-form-item label="日期">
        <el-date-picker
          v-model="dateInput"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择日期"
          style="width: 200px"
        />
      </el-form-item>
      <el-form-item label="内容">
        <MdEditor v-model="contentInput" :preview="false" style="height: 260px; width: 100%" />
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="onSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>
