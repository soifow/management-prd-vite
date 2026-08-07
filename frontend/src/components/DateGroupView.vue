<script setup lang="ts">
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useRequirementsStore } from '@/stores/requirements'
import { groupByDate } from '@/composables/useRequirementByDate'
import { STATUS_LABEL } from '@/types/requirement'
import type { RequirementItem, RequirementStatus } from '@/types'
import { formatDate } from '@/utils'

const store = useRequirementsStore()
const { filteredItems } = storeToRefs(store)

const groups = computed(() => groupByDate(filteredItems.value))

// 默认展开最新日期组（日期倒序，第一个就是最新）
const activeNames = ref<string[]>([])
watch(
  groups,
  (g) => {
    activeNames.value = g.length > 0 ? [g[0].date] : []
  },
  { immediate: true },
)

function onRowClick(item: RequirementItem) {
  store.openFeature(item.feature)
}

async function onStatusChange(item: RequirementItem, status: RequirementStatus) {
  await store.setIterationStatus(item.id, status)
}
</script>

<template>
  <div class="date-view">
    <el-empty v-if="groups.length === 0" description="暂无需求" />

    <el-collapse v-else v-model="activeNames" class="date-collapse">
      <el-collapse-item
        v-for="g in groups"
        :key="g.date"
        :name="g.date"
      >
        <template #title>
          <span class="date-title">
            {{ formatDate(g.date) }}
            <el-tag type="info" size="small" effect="plain" class="count-tag">
              {{ g.items.length }} 条
            </el-tag>
          </span>
        </template>

        <div
          v-for="seg in g.segments"
          :key="seg.module + g.date"
          class="segment"
        >
          <div class="segment-header">
            <el-tag type="warning" size="small" effect="plain">{{ seg.module }}</el-tag>
          </div>

          <el-card
            v-for="item in seg.items"
            :key="item.id"
            class="req-row"
            shadow="hover"
            @click="onRowClick(item)"
          >
            <div class="req-info">
              <span class="req-feature">{{ item.feature || '（未命名）' }}</span>
              <div class="req-meta">
                <el-tag
                  v-if="item.status === 'done'"
                  type="success"
                  size="small"
                  effect="light"
                  class="done-tag"
                >完成</el-tag>
                <span class="req-content" v-if="item.feature && item.feature !== item.content">
                  {{ item.content }}
                </span>
              </div>
            </div>

            <el-select
              :model-value="item.status"
              size="small"
              class="status-select"
              @click.stop
              @change="onStatusChange(item, $event as RequirementStatus)"
            >
              <el-option
                v-for="(label, key) in STATUS_LABEL"
                :key="key"
                :label="label"
                :value="key"
              />
            </el-select>
          </el-card>
        </div>
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
.segment {
  margin-bottom: 12px;
}
.segment-header {
  margin-bottom: 6px;
}
.req-row {
  margin-bottom: 8px;
  cursor: pointer;
  transition: box-shadow 0.2s;
}
/* 悬停：仅阴影浮现，边框与背景保持不变 */
.req-row.is-hover-shadow:hover,
.req-row.is-hover-shadow:focus {
  box-shadow:
    0 1px 2px rgba(0, 0, 0, 0.06),
    0 6px 16px rgba(0, 0, 0, 0.1);
}
.req-row :deep(.el-card__body) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  padding: 10px 12px;
}
.req-info {
  display: flex;
  flex-direction: column;
  gap: 2px;
  min-width: 0;
  flex: 1;
}
.req-meta {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}
.done-tag {
  flex-shrink: 0;
}
.req-feature {
  font-size: 14px;
  font-weight: 500;
  color: #1f2937;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.req-content {
  font-size: 12px;
  color: #6b7280;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  min-width: 0;
}
.status-select {
  width: 110px;
  flex-shrink: 0;
}
</style>
