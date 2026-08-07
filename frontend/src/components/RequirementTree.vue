<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useRequirementsStore } from '@/stores/requirements'
import { useSettingsStore } from '@/stores/settings'
import { buildFeatureTree, groupByModule } from '@/composables/useRequirementTree'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import { formatDate } from '@/utils'

const store = useRequirementsStore()
const settingsStore = useSettingsStore()
const { filteredItems, filters, currentProgressMap } = storeToRefs(store)
const { showSubitemProgressInTree } = storeToRefs(settingsStore)

const treeNodes = computed(() =>
  buildFeatureTree(
    filteredItems.value,
    filters.value,
    showSubitemProgressInTree.value ? currentProgressMap.value : {},
  ),
)
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

function onOpenFeature(feature: string) {
  store.openFeature(feature)
}
</script>

<template>
  <div class="tree-container">
    <el-empty v-if="grouped.length === 0" description="暂无需求" />

    <el-collapse v-else v-model="activeNames" class="module-collapse">
      <el-collapse-item v-for="g in grouped" :key="g.module" :name="g.module">
        <template #title>
          <span class="module-title">
            📦 {{ g.module }}
            <el-tag type="info" size="small" effect="plain" class="count-tag">
              {{ g.features.length }}
            </el-tag>
          </span>
        </template>

        <el-card
          v-for="f in g.features"
          :key="`${g.module}-${f.feature}`"
          class="feature-card"
          shadow="hover"
          @click="onOpenFeature(f.feature)"
        >
          <div class="feature-name">
            {{ f.feature || '（未命名）' }}
            <span
              v-if="showSubitemProgressInTree && f.subitemProgress"
              class="progress-badge"
            >
              {{ f.subitemProgress.done }}/{{ f.subitemProgress.total }}
            </span>
          </div>
          <div class="feature-meta">
            <el-tag :type="STATUS_TAG_TYPE[f.latestStatus] as never" size="small" effect="light">
              {{ STATUS_LABEL[f.latestStatus] }}
            </el-tag>
            <span class="meta-info">
              {{ f.count }} 次迭代 · 最新 {{ formatDate(f.latestDate) }}
            </span>
            <span class="arrow">›</span>
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
.feature-card {
  margin-bottom: 12px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
/* 悬停：仅阴影浮现，边框与背景保持不变 */
.feature-card.is-hover-shadow:hover,
.feature-card.is-hover-shadow:focus {
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.06),
    0 6px 16px rgba(0, 0, 0, 0.1);
}
.feature-card :deep(.el-card__body) {
  padding: 10px 14px;
}
.feature-name {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  margin-bottom: 4px;
}
.progress-badge {
  margin-left: 8px;
  font-size: 12px;
  color: #6b7280;
  font-weight: 400;
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
