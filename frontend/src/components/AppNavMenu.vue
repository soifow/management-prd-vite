<script setup lang="ts">
import { Bell, Document, Setting, WarningFilled } from '@element-plus/icons-vue'

defineProps<{ activeKey: 'workspace' | 'settings' | 'bug' }>()
const emit = defineEmits<{
  (e: 'select', key: 'workspace' | 'settings' | 'bug'): void
  (e: 'open-todo'): void
}>()

function onSelectWorkspace() {
  emit('select', 'workspace')
}
function onSelectBug() {
  emit('select', 'bug')
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
    <!-- 顶部：工作区 + Bug 管理（这两项受 activeKey 高亮控制） -->
    <el-menu class="nav-menu" :collapse="true" :default-active="activeKey">
      <el-menu-item index="workspace" @click="onSelectWorkspace">
        <el-icon><Document /></el-icon>
        <template #title>工作区</template>
      </el-menu-item>
      <el-menu-item index="bug" @click="onSelectBug">
        <el-icon><WarningFilled /></el-icon>
        <template #title>Bug 管理</template>
      </el-menu-item>
    </el-menu>

    <!--
      待办提醒：独立于 el-menu 容器之外。
      若放进 el-menu，被点击后 el-menu 内部 activeIndex 必然更新为 "todo"，
      强制菜单高亮跳到该 item（与 el-menu 是否受控无关）。但待办是覆盖在主 UI 上的抽屉，
      不应改变主 UI 高亮；故拆出 el-menu，做成普通项，模仿 .el-menu-item 折叠态样式。
    -->
    <el-tooltip content="待办提醒" placement="right">
      <div class="menu-item" @click="onOpenTodo">
        <el-icon><Bell /></el-icon>
      </div>
    </el-tooltip>

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
/* 拆出 el-menu 的待办提醒项：与 .el-menu-item 折叠态一致，hover 高亮（无 is-active，故永不高亮） */
.menu-item {
  color: #cbd5e1;
  height: 56px;
  line-height: 56px;
  width: 64px;
  text-align: center;
  cursor: pointer;
}
.menu-item:hover {
  background: #374151;
  color: #ffffff;
}
</style>

