<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { IPixelReload } from '@/constants/icons'

import { useTodoStore } from '@/stores/todo'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { formatDate } from '@/utils'
import type { TodoReminder } from '@/types'

const props = defineProps<{ modelValue: boolean }>()
const emit = defineEmits<{
  (e: 'update:modelValue', v: boolean): void
  (e: 'jump', item: TodoReminder): void
}>()

const todoStore = useTodoStore()
const { reminders, loading } = storeToRefs(todoStore)

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

interface TodoGroup {
  key: string
  label: string
  items: TodoReminder[]
}

/**
 * 按 bucket 与 remaining_days 分组。
 * 顺序：已逾期 → 剩余 N 天（按 N 升序，N=0 显示“今天到期”）→ 无时限 → 远期规划。
 */
const groups = computed<TodoGroup[]>(() => {
  const map = new Map<string, TodoGroup>()

  for (const item of reminders.value) {
    let key: string
    let label: string
    if (item.bucket === 'overdue') {
      key = 'overdue'
      label = '已逾期'
    } else if (item.bucket === 'remaining') {
      const n = item.remaining_days ?? 0
      key = `remaining-${n}`
      label = n === 0 ? '今天到期' : `剩余 ${n} 天`
    } else if (item.bucket === 'no_deadline') {
      key = 'no_deadline'
      label = '无时限'
    } else {
      key = 'deferred'
      label = '远期规划'
    }
    const group = map.get(key)
    if (group) {
      group.items.push(item)
    } else {
      map.set(key, { key, label, items: [item] })
    }
  }

  return Array.from(map.values())
})

const expandedGroups = ref<string[]>([])
watch(
  groups,
  (g) => {
    expandedGroups.value = g.map((x) => x.key)
  },
  { immediate: true },
)

function onRefresh() {
  void todoStore.load()
}

function onClickItem(item: TodoReminder) {
  emit('jump', item)
}
</script>

<template>
  <el-drawer
    v-model="visible"
    direction="rtl"
    size="380px"
    title="待办提醒"
    :destroy-on-close="false"
    class="todo-drawer"
  >
    <template #header>
      <div class="drawer-head">
        <span class="drawer-title">待办提醒</span>
        <el-button :icon="IPixelReload" link :loading="loading" @click="onRefresh">
          刷新
        </el-button>
      </div>
    </template>

    <div v-loading="loading" class="drawer-body">
      <el-empty v-if="groups.length === 0" description="暂无待办" />

      <el-collapse v-else v-model="expandedGroups" class="group-list">
        <el-collapse-item
          v-for="g in groups"
          :key="g.key"
          :name="g.key"
          :title="`${g.label} (${g.items.length})`"
        >
          <div
            v-for="item in g.items"
            :key="item.item_id"
            class="todo-card"
            @click="onClickItem(item)"
          >
            <div class="card-row meta">
              <span class="project-module">
                {{ item.project_name }}{{ item.module ? ` - ${item.module}` : '' }}
              </span>
              <span class="meta-tags">
                <el-tag v-if="item.subitem_id" size="small" type="info" effect="plain">子需求</el-tag>
                <el-tag :type="STATUS_TAG_TYPE[item.status]" size="small">
                  {{ STATUS_LABEL[item.status] }}
                </el-tag>
              </span>
            </div>
            <div v-if="item.feature" class="card-row feature">功能：{{ item.feature }}</div>
            <div class="card-row content">{{ item.content || '（空）' }}</div>
            <div v-if="item.completion_deadline" class="card-row deadline">
              🗓 {{ formatDate(item.completion_deadline) }}
            </div>
          </div>
        </el-collapse-item>
      </el-collapse>
    </div>
  </el-drawer>
</template>

<style scoped>
.drawer-head {
  display: flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  padding-right: 8px;
}
.drawer-title {
  font-weight: 600;
  font-size: 16px;
}
.drawer-body {
  height: 100%;
}
.group-list {
  --el-collapse-border-color: #e5e7eb;
  --el-collapse-header-height: 44px;
  --el-collapse-header-bg-color: #f9fafb;
  --el-collapse-content-bg-color: #ffffff;
}
.group-list :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 14px;
  color: #374151;
  padding: 0 12px;
}
.group-list :deep(.el-collapse-item__content) {
  padding: 8px 12px 12px;
}
.todo-card {
  padding: 10px 12px;
  margin-bottom: 8px;
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  background: #ffffff;
  cursor: pointer;
  transition: background 0.15s, border-color 0.15s;
}
.todo-card:hover {
  background: #f3f4f6;
  border-color: #d1d5db;
}
.todo-card:last-child {
  margin-bottom: 0;
}
.card-row {
  display: flex;
  align-items: center;
  gap: 8px;
}
.card-row.meta {
  justify-content: space-between;
  margin-bottom: 6px;
}
.project-module {
  font-size: 13px;
  font-weight: 500;
  color: #111827;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex: 1;
}
.meta-tags {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}
.card-row.feature {
  font-size: 12px;
  color: #6b7280;
  margin-top: 4px;
}
.card-row.content {
  font-size: 13px;
  color: #4b5563;
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}
.card-row.deadline {
  margin-top: 6px;
  font-size: 12px;
  color: #d97706;
}
</style>
