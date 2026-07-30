<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useBugsStore } from '@/stores/bugs'
import { BUG_STATUS_LABEL, BUG_STATUS_TAG_TYPE, LEVEL_LABEL, LEVEL_TAG_TYPE } from '@/types/bug'
import type { BugItem, BugStatus } from '@/types'
import { formatDate, sortBugs } from '@/utils'

const store = useBugsStore()
const { filteredBugs } = storeToRefs(store)

interface ModuleGroup {
  module: string
  bugs: BugItem[]
}

const grouped = computed<ModuleGroup[]>(() => {
  const map = new Map<string, BugItem[]>()
  for (const b of filteredBugs.value) {
    const key = b.module || '（未分组）'
    const list = map.get(key)
    if (list) list.push(b)
    else map.set(key, [b])
  }
  return Array.from(map.entries())
    .map(([module, bugs]) => ({ module, bugs: sortBugs(bugs) }))
    .sort((a, b) => a.module.localeCompare(b.module, 'zh-Hans-CN'))
})

const activeNames = ref<string[]>([])
// 默认只展开第一个模块
watch(
  grouped,
  (groups) => {
    activeNames.value = groups.length > 0 ? [groups[0].module] : []
  },
  { immediate: true },
)

function onOpenBug(id: string) {
  store.openBug(id)
}

async function onStatusChange(b: BugItem, status: BugStatus) {
  await store.setStatus(b.id, status)
}
</script>

<template>
  <div class="tree-container">
    <el-empty v-if="grouped.length === 0" description="暂无 bug" />

    <el-collapse v-else v-model="activeNames" class="module-collapse">
      <el-collapse-item v-for="g in grouped" :key="g.module" :name="g.module">
        <template #title>
          <span class="module-title">
            📦 {{ g.module }}
            <el-tag type="info" size="small" effect="plain" class="count-tag">
              {{ g.bugs.length }}
            </el-tag>
          </span>
        </template>

        <div
          v-for="b in g.bugs"
          :key="b.id"
          class="bug-card"
          @click="onOpenBug(b.id)"
        >
          <div class="bug-head">
            <span v-if="b.status === 'fixed'" class="fixed-badge">已修复</span>
            <el-tag :type="LEVEL_TAG_TYPE[b.level] as never" size="small" effect="dark">
              {{ LEVEL_LABEL[b.level] }}
            </el-tag>
            <el-tag :type="BUG_STATUS_TAG_TYPE[b.status] as never" size="small" effect="light">
              {{ BUG_STATUS_LABEL[b.status] }}
            </el-tag>
            <span class="bug-date">📅 {{ formatDate(b.date) }}</span>
          </div>
          <div class="bug-content">{{ b.content || '（空）' }}</div>
          <div class="bug-foot">
            <el-select
              :model-value="b.status"
              size="small"
              class="status-select"
              @click.stop
              @change="(v: BugStatus) => onStatusChange(b, v)"
            >
              <el-option
                v-for="(label, key) in BUG_STATUS_LABEL"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
          </div>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.tree-container {
  min-height: 200px;
}
.module-collapse {
  border: none;
}
.module-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 14px;
  background: #f9fafb;
  border-radius: 4px;
  padding: 0 8px;
  height: 36px;
}
.module-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  padding: 8px 0 0 16px;
}
.module-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.count-tag {
  margin-left: 4px;
}
.bug-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 14px;
  margin-bottom: 8px;
  cursor: pointer;
  transition: border-color 0.15s, background 0.15s;
}
.bug-card:hover {
  border-color: #409eff;
  background: #f5f9ff;
}
.bug-head {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 6px;
  flex-wrap: wrap;
}
.fixed-badge {
  font-size: 12px;
  font-weight: 600;
  color: #16a34a;
  background: #dcfce7;
  border: 1px solid #86efac;
  border-radius: 4px;
  padding: 1px 6px;
  line-height: 18px;
}
.bug-date {
  font-size: 12px;
  color: #d97706;
  font-weight: 500;
}
.bug-content {
  font-size: 13px;
  color: #374151;
  line-height: 1.5;
  margin-bottom: 8px;
  overflow: hidden;
  text-overflow: ellipsis;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
}
.bug-foot {
  display: flex;
  justify-content: flex-end;
}
.status-select {
  width: 110px;
}
</style>
