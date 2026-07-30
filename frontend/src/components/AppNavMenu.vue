<script setup lang="ts">
import { Bell, Document, Setting } from '@element-plus/icons-vue'

defineProps<{ activeKey: 'workspace' | 'settings' }>()
const emit = defineEmits<{
  (e: 'select', key: 'workspace' | 'settings'): void
  (e: 'open-todo'): void
}>()

function onSelectWorkspace() {
  emit('select', 'workspace')
}
function onSelectSettings() {
  emit('select', 'settings')
}
function onOpenTodo() {
  emit('open-todo')
}
</script>

<template>
  <el-aside width="64px" class="nav-col">
    <!-- 顶部：工作区 + 待办提醒 -->
    <el-menu class="nav-menu" :collapse="true" :default-active="activeKey">
      <el-menu-item index="workspace" @click="onSelectWorkspace">
        <el-icon><Document /></el-icon>
        <template #title>工作区</template>
      </el-menu-item>
      <el-menu-item index="todo" @click="onOpenTodo">
        <el-icon><Bell /></el-icon>
        <template #title>待办提醒</template>
      </el-menu-item>
    </el-menu>

    <div class="spacer" />

    <!-- 底部：设置 -->
    <el-menu class="nav-menu" :collapse="true" :default-active="activeKey">
      <el-menu-item index="settings" @click="onSelectSettings">
        <el-icon><Setting /></el-icon>
        <template #title>设置</template>
      </el-menu-item>
    </el-menu>
  </el-aside>
</template>

<style scoped>
.nav-col {
  background: #1f2937;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #111827;
  padding-bottom: 8px;
  overflow: hidden; /* 抑制底部横向滚动条：折叠菜单子项溢出不再撑出容器 */
}
.spacer {
  flex: 1;
}
.nav-menu {
  border-right: none;
  background: transparent;
  width: 64px;
  overflow: hidden;
}
.nav-menu :deep(.el-menu-item) {
  color: #cbd5e1;
  height: 56px;
  line-height: 56px;
  width: 64px;
}
.nav-menu :deep(.el-menu-item:hover) {
  background: #374151;
  color: #ffffff;
}
/* 折叠态下选中项高亮：工作区与设置共用同一份高亮逻辑 */
.nav-menu :deep(.el-menu-item.is-active) {
  color: #ffffff;
  background: #409eff;
}
</style>
