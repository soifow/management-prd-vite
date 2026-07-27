<script setup lang="ts">
import { onMounted, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'

import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import { whenReady } from '@/api'

import ProjectSidebar from '@/components/ProjectSidebar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import RequirementTree from '@/components/RequirementTree.vue'
import FeatureDetail from '@/components/FeatureDetail.vue'

const projectsStore = useProjectsStore()
const requirementsStore = useRequirementsStore()
const { activeProjectId } = storeToRefs(projectsStore)
const { selectedFeature } = storeToRefs(requirementsStore)

onMounted(async () => {
  try {
    await whenReady()
    await projectsStore.loadSummaries()
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '初始化失败')
  }
})

watch(activeProjectId, async (id) => {
  if (id) {
    try {
      await requirementsStore.loadProject(id)
    } catch (e) {
      ElMessage.error(e instanceof Error ? e.message : '加载项目失败')
    }
  }
})
</script>

<template>
  <el-container class="layout">
    <el-aside width="260px" class="aside">
      <ProjectSidebar />
    </el-aside>
    <el-main class="main">
      <FilterToolbar v-if="!selectedFeature" class="toolbar-sticky" />
      <div class="content" :class="{ 'content-full': selectedFeature }">
        <FeatureDetail v-if="selectedFeature" />
        <RequirementTree v-else />
      </div>
    </el-main>
  </el-container>
</template>

<style scoped>
.layout {
  height: 100%;
}
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
/* 顶部筛选栏：固顶，不随内容滚动 */
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
/* 详情页：撑满视口高度，内部走 flex 分配 */
.content-full {
  overflow: hidden;
  margin: 0;
  border-radius: 0;
  padding: 16px 20px;
  display: flex;
  flex-direction: column;
}
</style>
