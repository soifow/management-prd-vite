<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'
import { ElMessage } from 'element-plus'

import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import { useSettingsStore } from '@/stores/settings'
import { useTodoStore } from '@/stores/todo'
import { whenReady } from '@/api'

import AppNavMenu from '@/components/AppNavMenu.vue'
import ProjectSidebar from '@/components/ProjectSidebar.vue'
import FilterToolbar from '@/components/FilterToolbar.vue'
import RequirementTree from '@/components/RequirementTree.vue'
import DateGroupView from '@/components/DateGroupView.vue'
import FeatureDetail from '@/components/FeatureDetail.vue'
import SettingsPage from '@/components/SettingsPage.vue'
import TodoDrawer from '@/components/TodoDrawer.vue'
import type { TodoReminder } from '@/types'

const projectsStore = useProjectsStore()
const requirementsStore = useRequirementsStore()
const settingsStore = useSettingsStore()
const todoStore = useTodoStore()
const { activeProjectId } = storeToRefs(projectsStore)
const { selectedFeature, viewMode } = storeToRefs(requirementsStore)

/** 当前视图：workspace=工作区，settings=设置页 */
const currentView = ref<'workspace' | 'settings'>('workspace')

/** 待办抽屉显隐：启动后自动打开 */
const todoVisible = ref(false)

/**
 * 跨项目跳转守卫：true 时跳过 activeProjectId watch 触发的 loadProject。
 * 见 onJumpToItem —— 需要在切项目的同时 openFeature / selectIteration，
 * 避免被自动 reloadProject 把 selectedFeature 重置。
 */
const suppressProjectLoad = ref(false)

onMounted(async () => {
  try {
    await whenReady()
    // 并行加载项目列表与设置；设置就绪后初始化聚合视图
    await Promise.all([projectsStore.loadSummaries(), settingsStore.loadSettings()])
    requirementsStore.setViewMode(settingsStore.defaultViewMode)
    // 启动后加载待办并自动弹出抽屉
    await todoStore.load()
    todoVisible.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '初始化失败')
  }
})

watch(activeProjectId, async (id) => {
  // 跨项目跳转时由 onJumpToItem 统一处理，避免此处重新加载打断 openFeature
  if (suppressProjectLoad.value) return
  if (id) {
    try {
      await requirementsStore.loadProject(id)
    } catch (e) {
      ElMessage.error(e instanceof Error ? e.message : '加载项目失败')
    }
  } else {
    // 没有可用项目（如唯一项目被删除）：清空右侧数据，让 el-empty 显示
    requirementsStore.reset()
  }
})

function onNavSelect(key: 'workspace' | 'settings') {
  currentView.value = key
}

/** 设置页保存：切回工作区 */
function onSettingsSave() {
  currentView.value = 'workspace'
}

/** 手动重新打开待办抽屉（顶部菜单铃铛） */
async function onOpenTodo() {
  try {
    await todoStore.load()
    todoVisible.value = true
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '加载待办失败')
  }
}

/**
 * 点击待办条目：关闭抽屉、跨项目跳转、打开功能、选中迭代。
 * 用 suppressProjectLoad 守卫避免被 activeProjectId watch 打断。
 */
async function onJumpToItem(item: TodoReminder) {
  todoVisible.value = false
  currentView.value = 'workspace'
  suppressProjectLoad.value = true
  try {
    projectsStore.select(item.project_id)
    await requirementsStore.loadProject(item.project_id)
    await requirementsStore.openFeature(item.module, item.feature)
    requirementsStore.selectIteration(item.item_id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '跳转失败')
  } finally {
    suppressProjectLoad.value = false
  }
}
</script>

<template>
  <el-container class="layout">
    <AppNavMenu :active-key="currentView" @select="onNavSelect" @open-todo="onOpenTodo" />

    <!-- 设置页：替换整个右侧区域 -->
    <template v-if="currentView === 'settings'">
      <SettingsPage @save="onSettingsSave" />
    </template>

    <!-- 工作区：项目侧边栏 + 主内容 -->
    <template v-else>
      <el-aside width="210px" class="aside">
        <ProjectSidebar />
      </el-aside>
      <el-main class="main">
        <FilterToolbar v-if="!selectedFeature" class="toolbar-sticky" />
        <div class="content" :class="{ 'content-full': selectedFeature }">
          <FeatureDetail v-if="selectedFeature" />
          <DateGroupView v-else-if="viewMode === 'date'" />
          <RequirementTree v-else />
        </div>
      </el-main>
    </template>

    <TodoDrawer v-model="todoVisible" @jump="onJumpToItem" />
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
