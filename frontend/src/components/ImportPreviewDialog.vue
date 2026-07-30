<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

import { useRequirementsStore } from '@/stores/requirements'
import { useProjectsStore } from '@/stores/projects'
import type { RequirementStatus, ParsedRequirement } from '@/types'
import { STATUS_LABEL } from '@/types/requirement'

const store = useRequirementsStore()
const projectsStore = useProjectsStore()
const visible = ref(false)
const requirements = ref<ParsedRequirement[]>([])
const defaultStatus = ref<RequirementStatus>('done')

// 导入模式：current=导入当前项目；new=新建项目并导入（项目名可编辑，取自文件名）
const mode = ref<'current' | 'new'>('current')
const projectName = ref('')

const dialogTitle = computed(() =>
  mode.value === 'new' ? '导入新建项目' : '导入当前项目',
)

// 按模块分组展示
const grouped = computed(() => {
  const m = new Map<string, ParsedRequirement[]>()
  for (const r of requirements.value) {
    const key = r.module || '（未分组）'
    if (!m.has(key)) m.set(key, [])
    m.get(key)!.push(r)
  }
  return Array.from(m.entries())
})

const statusOptions: RequirementStatus[] = [
  'todo',
  'ui_done_waiting_backend',
  'done',
  'deferred',
]

function open(parsed: ParsedRequirement[], m: 'current' | 'new' = 'current', filename = '') {
  requirements.value = parsed.map((r) => ({ ...r }))
  defaultStatus.value = 'done'
  mode.value = m
  projectName.value = filename
  visible.value = true
}

defineExpose({ open })

function applyDefaultStatus() {
  // 把非 to do（status 来自 to do 段的项保留）的项设为默认状态
  for (const r of requirements.value) {
    // 仅当解析为 done（即默认）时才覆盖为用户选的默认状态
    if (r.status === 'done') {
      r.status = defaultStatus.value
    }
  }
}

async function onApply() {
  const selected = requirements.value.filter((r) => r.selected)
  if (selected.length === 0) {
    ElMessage.warning('请至少选择一项')
    return
  }
  if (mode.value === 'new' && !projectName.value.trim()) {
    ElMessage.warning('项目名不能为空')
    return
  }
  try {
    if (mode.value === 'new') {
      const project = await store.applyAsNewProject(projectName.value.trim(), selected)
      // 刷新左侧列表并选中新项目
      await projectsStore.loadSummaries()
      projectsStore.select(project.id)
      ElMessage.success(`已新建项目「${project.name}」并导入 ${selected.length} 条需求`)
    } else {
      await store.apply(selected)
      ElMessage.success(`已导入 ${selected.length} 条需求`)
    }
    visible.value = false
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '导入失败')
  }
}

function toggleGroup(items: ParsedRequirement[], val: boolean) {
  for (const it of items) it.selected = val
}
</script>

<template>
  <el-dialog v-model="visible" :title="dialogTitle" width="720px">
    <div v-if="mode === 'new'" class="name-row">
      <span class="label">项目名：</span>
      <el-input v-model="projectName" placeholder="项目名（取自导入文件名，可修改）" style="width: 320px" />
    </div>

    <div class="bar">
      <span class="label">默认状态（应用于非 to do 段的项）：</span>
      <el-select v-model="defaultStatus" style="width: 160px" @change="applyDefaultStatus">
        <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
      </el-select>
      <span class="hint">共 {{ requirements.length }} 条，已选
        {{ requirements.filter((r) => r.selected).length }}</span>
    </div>

    <div class="groups">
      <el-card v-for="[moduleName, reqs] in grouped" :key="moduleName" class="group" shadow="never">
        <div class="group-head">
          <el-checkbox
            :model-value="reqs.every((r) => r.selected)"
            @update:model-value="(v: boolean) => toggleGroup(reqs, v)"
          />
          <span class="group-name">{{ moduleName }}</span>
          <el-tag type="info" size="small" effect="plain">{{ reqs.length }}</el-tag>
        </div>
        <div v-for="(r, idx) in reqs" :key="idx" class="req-row">
          <el-checkbox v-model="r.selected" />
          <span class="req-content">{{ r.content }}</span>
          <el-select v-model="r.status" size="small" style="width: 150px">
            <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
          </el-select>
          <span class="req-date">
            {{ r.date ? r.date.slice(2).replace(/-/g, '') : '' }}
          </span>
        </div>
      </el-card>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onApply">
        {{ mode === 'new' ? '新建并导入' : '应用导入' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.name-row {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
}
.bar {
  display: flex;
  align-items: center;
  gap: 10px;
  margin-bottom: 16px;
  flex-wrap: wrap;
}
.label {
  font-size: 13px;
  color: #374151;
}
.hint {
  margin-left: auto;
  font-size: 12px;
  color: #6b7280;
}
.groups {
  max-height: 480px;
  overflow: auto;
}
.group {
  margin-bottom: 16px;
}
.group :deep(.el-card__body) {
  padding: 10px 14px;
}
.group-head {
  display: flex;
  align-items: center;
  gap: 8px;
  padding-bottom: 6px;
  border-bottom: 1px solid #f3f4f6;
}
.group-name {
  font-weight: 600;
  font-size: 14px;
}
.req-row {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 6px 0;
}
.req-content {
  flex: 1;
  font-size: 13px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.req-date {
  font-size: 12px;
  color: #d97706;
  min-width: 80px;
  text-align: right;
}
</style>
