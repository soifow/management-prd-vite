<script setup lang="ts">
import { ref, computed } from 'vue'
import { ElMessage } from 'element-plus'

import { useRequirementsStore } from '@/stores/requirements'
import type { RequirementStatus, ParsedRequirement } from '@/types'
import { STATUS_LABEL } from '@/types/requirement'

const store = useRequirementsStore()
const visible = ref(false)
const requirements = ref<ParsedRequirement[]>([])
const defaultStatus = ref<RequirementStatus>('done')

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

function open(parsed: ParsedRequirement[]) {
  requirements.value = parsed.map((r) => ({ ...r }))
  defaultStatus.value = 'done'
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
  try {
    await store.apply(selected)
    ElMessage.success(`已导入 ${selected.length} 条需求`)
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
  <el-dialog v-model="visible" title="导入预览" width="720px">
    <div class="bar">
      <span class="label">默认状态（应用于非 to do 段的项）：</span>
      <el-select v-model="defaultStatus" style="width: 160px" @change="applyDefaultStatus">
        <el-option v-for="s in statusOptions" :key="s" :label="STATUS_LABEL[s]" :value="s" />
      </el-select>
      <span class="hint">共 {{ requirements.length }} 条，已选
        {{ requirements.filter((r) => r.selected).length }}</span>
    </div>

    <div class="groups">
      <div v-for="[moduleName, reqs] in grouped" :key="moduleName" class="group">
        <div class="group-head">
          <el-checkbox
            :model-value="reqs.every((r) => r.selected)"
            @update:model-value="(v: boolean) => toggleGroup(reqs, v)"
          />
          <span class="group-name">{{ moduleName }}</span>
          <span class="group-count">{{ reqs.length }}</span>
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
      </div>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" @click="onApply">应用导入</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
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
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 8px 12px;
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
.group-count {
  background: #e5e7eb;
  border-radius: 10px;
  padding: 0 8px;
  font-size: 12px;
  color: #6b7280;
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
