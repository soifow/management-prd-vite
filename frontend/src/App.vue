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
import BugPage from '@/components/BugPage.vue'
import TodoDrawer from '@/components/TodoDrawer.vue'
import type { BugLinkInfo, TodoReminder } from '@/types'

const projectsStore = useProjectsStore()
const requirementsStore = useRequirementsStore()
const settingsStore = useSettingsStore()
const todoStore = useTodoStore()
const { activeProjectId } = storeToRefs(projectsStore)
const { selectedFeature, viewMode } = storeToRefs(requirementsStore)
const { reminders } = storeToRefs(todoStore)

/** 当前视图：workspace=工作区，bug=Bug 管理，settings=设置页 */
const currentView = ref<'workspace' | 'bug' | 'settings'>('workspace')

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
    // 启动后加载待办；仅当存在待办提醒时才自动弹出抽屉，空列表不打扰
    await todoStore.load()
    if (reminders.value.length > 0) {
      todoVisible.value = true
    }
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

function onNavSelect(key: 'workspace' | 'bug' | 'settings') {
  currentView.value = key
}

/** 设置页保存：切回工作区 */
function onSettingsSave() {
  currentView.value = 'workspace'
}

/**
 * Bug 详情「跳转查看关联迭代」：切到工作区、定位到对应需求迭代。
 * 复用 suppressProjectLoad 守卫避免被 activeProjectId watch 打断（同 onJumpToItem）。
 */
async function onJumpToRequirement(link: BugLinkInfo) {
  currentView.value = 'workspace'
  suppressProjectLoad.value = true
  try {
    projectsStore.select(link.project_id)
    await requirementsStore.loadProject(link.project_id)
    await requirementsStore.openFeature(link.feature)
    requirementsStore.selectIteration(link.item_id)
  } catch (e) {
    ElMessage.error(e instanceof Error ? e.message : '跳转失败')
  } finally {
    suppressProjectLoad.value = false
  }
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
    await requirementsStore.openFeature(item.feature)
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

    <!--
      三个视图常驻、用 v-show 切显隐（而非 v-if 互斥渲染）：
      切走不卸载、切回不重建，避免 FeatureDetail / md-editor-v3 反复挂载导致性能累积下降，
      并保留工作区状态（选中功能/迭代/子需求），杜绝切回后详情页空白。
      .view 作为 flex 行容器承载各视图内部的 el-aside + el-main。
    -->
    <div v-show="currentView === 'settings'" class="view">
      <SettingsPage @save="onSettingsSave" />
    </div>

    <div v-show="currentView === 'bug'" class="view">
      <BugPage @jump-requirement="onJumpToRequirement" />
    </div>

    <div v-show="currentView === 'workspace'" class="view">
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
    </div>

    <TodoDrawer v-model="todoVisible" @jump="onJumpToItem" />
  </el-container>
</template>

<style scoped>
.layout {
  height: 100%;
}
/* 视图容器：与 el-container 同向 flex 行，承接各视图内部 el-aside + el-main */
.view {
  flex: 1;
  display: flex;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
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
