<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { MdEditor } from 'md-editor-v3'

import { MD_EDITOR_PROPS } from '@/constants/md-editor'
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
const { modules, selectedFeature, selectedIteration } = storeToRefs(requirementsStore)

// 模块名候选（来自 modules 一等实体表）
const moduleOptions = computed(() => modules.value.map((m) => m.name))

const moduleNames = ref<string[]>([])
const featureInput = ref('')
const contentInput = ref('')
const statusInput = ref<RequirementStatus>('todo')
const dateInput = ref(isoDate(new Date()))
/** 完成时限（null = 无时限） */
const deadlineInput = ref<string | null>(null)
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
  featureOptions.value = await requirementsStore.listFeatures(activeProjectId.value)
}

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) return
    if (props.mode === 'edit' && editingItem.value) {
      moduleNames.value = [...editingItem.value.modules]
      featureInput.value = editingItem.value.feature
      contentInput.value = editingItem.value.content
      statusInput.value = editingItem.value.status
      dateInput.value = editingItem.value.date
      deadlineInput.value = editingItem.value.completion_deadline
    } else {
      // 新建：详情页入口预填当前迭代的模块与功能名（与功能名预填同源：selectedFeature 有值即详情页）；
      // 主界面「+需求」入口 selectedFeature 为 null，模块与功能名均不预填，保持原逻辑。
      moduleNames.value = selectedIteration.value ? [...selectedIteration.value.modules] : []
      featureInput.value = selectedFeature.value?.feature ?? ''
      contentInput.value = ''
      statusInput.value = 'todo'
      dateInput.value = isoDate(new Date())
      deadlineInput.value = null
    }
    await refreshFeatureOptions()
  },
)

// 暂缓状态联动清空时限（前端即时反馈；后端亦强制）
watch(statusInput, (s) => {
  if (s === 'deferred') deadlineInput.value = null
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
  if (moduleNames.value.length === 0) {
    ElMessage.warning('至少选择一个模块')
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
        module_names: moduleNames.value,
        feature: featureInput.value || contentInput.value.trim(),
        content: contentInput.value,
        status: statusInput.value,
        date: dateInput.value,
        completion_deadline: deadlineInput.value,
      })
      ElMessage.success('已新建迭代')
    } else if (editingItem.value) {
      await requirementsStore.updateIteration(editingItem.value.id, {
        module_names: moduleNames.value,
        feature: featureInput.value,
        content: contentInput.value,
        status: statusInput.value,
        date: dateInput.value,
        completion_deadline: deadlineInput.value ?? undefined,
        clear_completion_deadline: deadlineInput.value === null,
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
    align-center
    destroy-on-close
    class="edit-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-form label-width="80px">
      <el-form-item label="模块" required>
        <el-select
          v-model="moduleNames"
          multiple
          filterable
          allow-create
          default-first-option
          placeholder="选择或输入模块（可多选）"
          style="width: 100%"
        >
          <el-option v-for="m in moduleOptions" :key="m" :label="m" :value="m" />
        </el-select>
      </el-form-item>
      <el-form-item label="功能名">
        <el-select
          v-model="featureInput"
          filterable
          allow-create
          default-first-option
          clearable
          placeholder="选择或输入功能名（同名功能聚合为迭代）"
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
      <el-form-item label="完成时限">
        <el-date-picker
          v-model="deadlineInput"
          type="date"
          value-format="YYYY-MM-DD"
          clearable
          placeholder="选填，留空表示无时限"
          style="width: 200px"
          :disabled="statusInput === 'deferred'"
        />
      </el-form-item>
      <el-form-item label="内容">
        <div class="editor-wrapper">
          <MdEditor v-model="contentInput" v-bind="MD_EDITOR_PROPS" />
        </div>
      </el-form-item>
    </el-form>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" @click="onSubmit">保存</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
/* 弹窗 body 限高防溢出，避免不必要的纵向滚动条 */
.edit-dialog :deep(.el-dialog__body) {
  max-height: 70vh;
  overflow-y: auto;
  padding-bottom: 10px;
}
/* md-editor 包裹：固定高度，编辑器 100% 自适应 */
.editor-wrapper {
  width: 100%;
  height: 320px;
  overflow: hidden;
}
.editor-wrapper :deep(.md-editor) {
  height: 100%;
}
/* md-editor footer 字数统计垂直居中：见 styles/main.css 全局规则（弹窗/详情页统一处理） */
</style>
