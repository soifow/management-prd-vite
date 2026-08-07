<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useBugsStore } from '@/stores/bugs'
import { BUG_STATUS_LABEL, LEVEL_LABEL, LEVEL_TAG_TYPE } from '@/types/bug'
import type { BugItem, BugStatus } from '@/types'
import { formatDate, sortBugs } from '@/utils'

const store = useBugsStore()
const { filteredBugs } = storeToRefs(store)

interface DateGroup {
  date: string
  bugs: BugItem[]
}

const groups = computed<DateGroup[]>(() => {
  const map = new Map<string, BugItem[]>()
  for (const b of filteredBugs.value) {
    const list = map.get(b.date)
    if (list) list.push(b)
    else map.set(b.date, [b])
  }
  return Array.from(map.entries())
    .map(([date, bugs]) => ({ date, bugs: sortBugs(bugs) }))
    .sort((a, b) => b.date.localeCompare(a.date))
})

const activeNames = ref<string[]>([])
watch(
  groups,
  (g) => {
    activeNames.value = g.length > 0 ? [g[0].date] : []
  },
  { immediate: true },
)

function onOpenBug(b: BugItem) {
  store.openBug(b.id)
}

async function onStatusChange(b: BugItem, status: BugStatus) {
  await store.setStatus(b.id, status)
}
</script>

<template>
  <div class="date-view">
    <el-empty v-if="groups.length === 0" description="暂无 bug" />

    <el-collapse v-else v-model="activeNames" class="date-collapse">
      <el-collapse-item v-for="g in groups" :key="g.date" :name="g.date">
        <template #title>
          <span class="date-title">
            {{ formatDate(g.date) }}
            <el-tag type="info" size="small" effect="plain" class="count-tag">
              {{ g.bugs.length }} 条
            </el-tag>
          </span>
        </template>

        <el-card
          v-for="b in g.bugs"
          :key="b.id"
          class="bug-row"
          shadow="hover"
          @click="onOpenBug(b)"
        >
          <div class="bug-info">
            <div class="bug-head">
              <span v-if="b.status === 'fixed'" class="fixed-badge">已修复</span>
              <el-tag :type="LEVEL_TAG_TYPE[b.level] as never" size="small" effect="dark">
                {{ LEVEL_LABEL[b.level] }}
              </el-tag>
              <span class="bug-module">{{ b.modules.join(' / ') || '（未分组）' }}</span>
            </div>
            <span class="bug-content">{{ b.content || '（空）' }}</span>
          </div>

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
        </el-card>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<style scoped>
.date-view {
  min-height: 200px;
}
.date-collapse {
  border: none;
}
.date-collapse :deep(.el-collapse-item__header) {
  font-weight: 600;
  font-size: 15px;
  background: #f9fafb;
  border-radius: 4px;
  padding: 0 8px;
  height: 40px;
}
.date-collapse :deep(.el-collapse-item__wrap) {
  border: none;
  /* 右/下留出空间，让卡片悬停阴影不被 overflow:hidden 裁剪 */
  padding: 8px 12px 12px 16px;
}
.date-title {
  display: flex;
  align-items: center;
  gap: 8px;
}
.count-tag {
  margin-left: 4px;
}
.bug-row {
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
/* 悬停：仅阴影浮现，边框与背景保持不变 */
.bug-row.is-hover-shadow:hover,
.bug-row.is-hover-shadow:focus {
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.06),
    0 6px 16px rgba(0, 0, 0, 0.1);
}
.bug-row :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
}
.bug-info {
  display: flex;
  flex-direction: column;
  gap: 4px;
  min-width: 0;
  flex: 1;
}
.bug-head {
  display: flex;
  align-items: center;
  gap: 8px;
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
.bug-module {
  font-size: 12px;
  color: #6b7280;
  font-weight: 500;
}
.bug-content {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.status-select {
  width: 110px;
  flex-shrink: 0;
}
</style>
