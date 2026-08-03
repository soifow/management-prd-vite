<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'
import { MdEditor } from 'md-editor-v3'

import { MD_EDITOR_PROPS } from '@/constants/md-editor'
import { useProjectsStore } from '@/stores/projects'
import { useBugsStore } from '@/stores/bugs'
import { LEVEL_LABEL } from '@/types/bug'
import { BUG_STATUS_LABEL } from '@/types/bug'
import type { BugLevel, BugStatus } from '@/types'
import { isoDate } from '@/utils'

const props = defineProps<{
  modelValue: boolean
  mode: 'create' | 'edit'
  bugId?: string
}>()

const emit = defineEmits<{ (e: 'update:modelValue', v: boolean): void }>()

const projectsStore = useProjectsStore()
const bugsStore = useBugsStore()
const { activeProjectId } = storeToRefs(projectsStore)
const { modules } = storeToRefs(bugsStore)

const moduleOptions = computed(() => modules.value.map((m) => m.name))
const moduleNames = ref<string[]>([])
const contentInput = ref('')
const levelInput = ref<BugLevel>('P3')
const statusInput = ref<BugStatus>('open')
const dateInput = ref(isoDate(new Date()))
const linkedId = ref<string | null>(null)
const clearLinked = ref(false)
const linkedFeature = ref('')

const features = ref<string[]>([])
const iterations = ref<{ id: string; date: string; content: string }[]>([])

const levelOptions: { value: BugLevel; label: string }[] = (
  Object.keys(LEVEL_LABEL) as BugLevel[]
).map((k) => ({ value: k, label: LEVEL_LABEL[k] }))

async function refreshFeatures() {
  if (!activeProjectId.value) {
    features.value = []
    return
  }
  features.value = await bugsStore.listFeaturesFor()
}

async function refreshIterations(feature: string) {
  if (!activeProjectId.value || !feature) {
    iterations.value = []
    return
  }
  const iters = await bugsStore.listIterationsFor(feature)
  iterations.value = iters.map((i) => ({ id: i.id, date: i.date, content: i.content }))
}

function reset() {
  moduleNames.value = modules.value.length > 0 ? [modules.value[0].name] : []
  contentInput.value = ''
  levelInput.value = 'P3'
  statusInput.value = 'open'
  dateInput.value = isoDate(new Date())
  linkedId.value = null
  clearLinked.value = false
  linkedFeature.value = ''
  features.value = []
  iterations.value = []
}

watch(
  () => props.modelValue,
  async (visible) => {
    if (!visible) return
    reset()
    await refreshFeatures()
  },
)

watch(linkedFeature, (f) => {
  if (f) void refreshIterations(f)
})

function onIterationChange(id: string | null) {
  linkedId.value = id
  clearLinked.value = false
}

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
    ElMessage.warning('bug 内容不能为空')
    return
  }
  if (!dateInput.value) {
    ElMessage.warning('请选择日期')
    return
  }
  try {
    await bugsStore.createBugItem({
      module_names: moduleNames.value,
      content: contentInput.value,
      level: levelInput.value,
      status: statusInput.value,
      date: dateInput.value,
      linked_iteration_id: linkedId.value,
    })
    ElMessage.success('已新建 bug')
    emit('update:modelValue', false)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '保存失败')
  }
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    title="新建 Bug"
    width="720px"
    align-center
    destroy-on-close
    class="edit-dialog"
    @update:model-value="(v: boolean) => emit('update:modelValue', v)"
  >
    <el-form label-width="90px">
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

      <el-form-item label="级别" required>
        <el-select v-model="levelInput" style="width: 100%">
          <el-option v-for="opt in levelOptions" :key="opt.value" :label="opt.label" :value="opt.value" />
        </el-select>
      </el-form-item>

      <el-form-item label="状态">
        <el-select v-model="statusInput" style="width: 100%">
          <el-option
            v-for="(label, key) in BUG_STATUS_LABEL"
            :key="key"
            :label="label"
            :value="key"
          />
        </el-select>
      </el-form-item>

      <el-form-item label="日期">
        <el-date-picker
          v-model="dateInput"
          type="date"
          value-format="YYYY-MM-DD"
          placeholder="选择 bug 日期"
          style="width: 200px"
        />
      </el-form-item>

      <el-form-item label="关联迭代">
        <div class="link-pickers">
          <el-select
            v-model="linkedFeature"
            clearable
            filterable
            placeholder="选填：选择功能"
            style="flex: 1"
          >
            <el-option v-for="f in features" :key="f" :label="f" :value="f" />
          </el-select>
          <el-select
            :model-value="linkedId"
            clearable
            placeholder="选填：选择迭代"
            style="flex: 1"
            @change="onIterationChange"
          >
            <el-option
              v-for="it in iterations"
              :key="it.id"
              :label="`${it.date.slice(0,10)} · ${it.content.slice(0,16)}`"
              :value="it.id"
            />
          </el-select>
        </div>
      </el-form-item>

      <el-form-item label="详细内容" required>
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
.edit-dialog :deep(.el-dialog__body) {
  max-height: 70vh;
  overflow-y: auto;
  padding-bottom: 10px;
}
.editor-wrapper {
  width: 100%;
  height: 320px;
  overflow: hidden;
}
.editor-wrapper :deep(.md-editor) {
  height: 100%;
}
/* md-editor footer 字数统计垂直居中：见 styles/main.css 全局规则（弹窗/详情页统一处理） */
.link-pickers {
  display: flex;
  gap: 10px;
  width: 100%;
}
</style>
