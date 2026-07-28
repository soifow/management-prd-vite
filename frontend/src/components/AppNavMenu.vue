<script setup lang="ts">
import { Document, Setting } from '@element-plus/icons-vue'

// 选中事件交给父组件处理：workspace=无操作（已在工作区），settings=打开设置弹窗
const emit = defineEmits<{ (e: 'select', key: 'workspace' | 'settings'): void }>()

function onSelectWorkspace() {
  emit('select', 'workspace')
}
function onSelectSettings() {
  emit('select', 'settings')
}
</script>

<template>
  <el-aside width="64px" class="nav-col">
    <!-- 顶部：工作区（默认选中） -->
    <el-menu class="nav-menu" :collapse="true" :default-active="'workspace'">
      <el-menu-item index="workspace" @click="onSelectWorkspace">
        <el-icon><Document /></el-icon>
        <template #title>工作区</template>
      </el-menu-item>
    </el-menu>

    <div class="spacer" />

    <!-- 底部：设置（动作型菜单，点击仅打开弹窗，不进入选中态） -->
    <el-menu class="nav-menu is-settings" :collapse="true">
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
/* 折叠态下选中项高亮 */
.nav-menu :deep(.el-menu-item.is-active) {
  color: #ffffff;
  background: #409eff;
}
/* 设置项点击后不应保留蓝色激活态：弹窗关闭后回到深色背景 */
.nav-menu.is-settings :deep(.el-menu-item.is-active) {
  color: #cbd5e1;
  background: transparent;
}
.nav-menu.is-settings :deep(.el-menu-item.is-active:hover) {
  background: #374151;
  color: #ffffff;
}
</style>
