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
    // 多模块展开：一条多模块 bug 在每个关联模块下各出现一份（底层同一记录）
    const mods = b.modules.length > 0 ? b.modules : ['（未分组）']
    for (const m of mods) {
      const key = m
      const list = map.get(key)
      if (list) {
        if (!list.some((x) => x.id === b.id)) list.push(b)
      } else {
        map.set(key, [b])
      }
    }
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

        <el-card
          v-for="b in g.bugs"
          :key="b.id"
          class="bug-card"
          shadow="hover"
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
        </el-card>
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
  /* 右/下留出空间，让卡片悬停阴影不被 overflow:hidden 裁剪 */
  padding: 8px 12px 12px 16px;
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
  margin-bottom: 12px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
/* 悬停：仅阴影浮现，边框与背景保持不变 */
.bug-card.is-hover-shadow:hover,
.bug-card.is-hover-shadow:focus {
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.06),
    0 6px 16px rgba(0, 0, 0, 0.1);
}
.bug-card :deep(.el-card__body) {
  padding: 10px 14px;
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
