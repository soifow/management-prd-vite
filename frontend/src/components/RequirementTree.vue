<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'

import { useRequirementsStore } from '@/stores/requirements'
import { buildFeatureTree, groupByModule } from '@/composables/useRequirementTree'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { formatYymmdd } from '@/utils'

const store = useRequirementsStore()
const { filteredItems, filters } = storeToRefs(store)

const treeNodes = computed(() => buildFeatureTree(filteredItems.value, filters.value))
const grouped = computed(() => groupByModule(treeNodes.value))

function onOpenFeature(module: string, feature: string) {
  store.openFeature(module, feature)
}
</script>

<template>
  <div class="tree-container">
    <el-empty v-if="grouped.length === 0" description="暂无需求" />

    <div v-for="g in grouped" :key="g.module" class="module-group">
      <div class="module-title">
        <span>📦 {{ g.module }}</span>
        <span class="count">{{ g.features.length }}</span>
      </div>

      <div
        v-for="f in g.features"
        :key="`${f.module}-${f.feature}`"
        class="feature-card"
        @click="onOpenFeature(f.module, f.feature)"
      >
        <div class="feature-name">{{ f.feature || '（未命名）' }}</div>
        <div class="feature-meta">
          <el-tag :type="STATUS_TAG_TYPE[f.latestStatus] as never" size="small" effect="light">
            {{ STATUS_LABEL[f.latestStatus] }}
          </el-tag>
          <span class="meta-info">
            {{ f.count }} 次迭代 · 最新 {{ formatYymmdd(f.latestDate) }}
          </span>
          <span class="arrow">›</span>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.tree-container {
  min-height: 200px;
}
.module-group {
  margin-bottom: 20px;
}
.module-title {
  font-weight: 600;
  font-size: 14px;
  color: #374151;
  padding: 6px 8px;
  background: #f9fafb;
  border-radius: 4px;
  margin-bottom: 8px;
  display: flex;
  justify-content: space-between;
  align-items: center;
}
.count {
  background: #e5e7eb;
  color: #6b7280;
  border-radius: 10px;
  padding: 0 8px;
  font-size: 12px;
}
.feature-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 14px;
  margin-left: 16px;
  margin-bottom: 8px;
  cursor: pointer;
  transition:
    border-color 0.15s,
    background 0.15s;
}
.feature-card:hover {
  border-color: #409eff;
  background: #f5f9ff;
}
.feature-name {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  margin-bottom: 4px;
}
.feature-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 12px;
  color: #6b7280;
}
.meta-info {
  flex: 1;
}
.arrow {
  color: #9ca3af;
  font-size: 18px;
}
</style>
