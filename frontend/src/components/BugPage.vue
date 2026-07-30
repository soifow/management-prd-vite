<script setup lang="ts">
import { storeToRefs } from 'pinia'

import { useBugsStore } from '@/stores/bugs'
import BugSidebar from '@/components/BugSidebar.vue'
import BugToolbar from '@/components/BugToolbar.vue'
import BugTree from '@/components/BugTree.vue'
import BugDateView from '@/components/BugDateView.vue'
import BugDetail from '@/components/BugDetail.vue'
import type { BugLinkInfo } from '@/types'

defineEmits<{ (e: 'jump-requirement', link: BugLinkInfo): void }>()

const bugsStore = useBugsStore()
const { currentBug, viewMode } = storeToRefs(bugsStore)
</script>

<template>
  <el-aside width="210px" class="aside">
    <BugSidebar />
  </el-aside>
  <el-main class="main">
    <BugToolbar v-if="!currentBug" class="toolbar-sticky" />
    <div class="content" :class="{ 'content-full': currentBug }">
      <BugDetail v-if="currentBug" @jump-requirement="$emit('jump-requirement', $event)" />
      <BugDateView v-else-if="viewMode === 'date'" />
      <BugTree v-else />
    </div>
  </el-main>
</template>

<style scoped>
.aside {
  background: #ffffff;
  border-right: 1px solid #e5e7eb;
  overflow: auto;
}
.main {
  padding: 0;
  overflow: hidden;
  background: #f5f7fa;
  display: flex;
  flex-direction: column;
}
.toolbar-sticky {
  position: sticky;
  top: 0;
  z-index: 10;
  flex-shrink: 0;
  padding: 12px 20px;
  background: #f5f7fa;
  margin-bottom: 0;
}
.content {
  flex: 1;
  min-height: 0;
  overflow: auto;
  background: #ffffff;
  border-radius: 6px;
  margin: 0 20px 16px;
  padding: 16px;
  box-shadow: 0 1px 2px rgba(0, 0, 0, 0.04);
}
.content-full {
  overflow: hidden;
  margin: 0;
  border-radius: 0;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
}
</style>
