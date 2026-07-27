<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useRequirementsStore } from '@/stores/requirements'
import { buildFeatureTree, groupByModule } from '@/composables/useRequirementTree'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { formatYymmdd } from '@/utils'

const store = useRequirementsStore()
const { filteredItems, filters } = storeToRefs(store)

const treeNodes = computed(() => buildFeatureTree(filteredItems.value, filters.value))
const grouped = computed(() => groupByModule(treeNodes.value))

// 折叠面板展开的模块名数组（可写 ref，v-model 需要）
const activeNames = ref<string[]>([])

watch(
  grouped,
  (groups) => {
    // 默认只展开第一个分组，其余折叠
    activeNames.value = groups.length > 0 ? [groups[0].module] : []
  },
  { immediate: true },
)

function onOpenFeature(module: string, feature: string) {
  store.openFeature(module, feature)
}
</script>

<template>
  <div class="tree-container">
    <el-empty v-if="grouped.length === 0" description="暂无需求" />

    <el-collapse v-else v-model="activeNames" class="module-collapse">
      <el-collapse-item
        v-for="g in grouped"
        :key="g.module"
        :name="g.module"
      >
        <template #title>
          <span class="module-title">
            📦 {{ g.module }}
            <el-tag type="info" size="small" effect="plain" class="count-tag">
              {{ g.features.length }}
            </el-tag>
          </span>
        </template>

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
/* 去掉 collapse-item 默认底边距，用模块间距替代 */
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
.feature-card {
  border: 1px solid #e5e7eb;
  border-radius: 6px;
  padding: 10px 14px;
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
