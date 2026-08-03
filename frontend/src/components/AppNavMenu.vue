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
    <!--
      导航项统一用自定义 .menu-item，高亮 class 由 activeKey 直接计算。
      不使用 el-menu：el-menu 的 default-active 受控高亮在多实例 + collapse 模式下
      存在内部 activeIndex 与 click/watcher 的时序竞态，会导致「点工作区但 bug 仍高亮」。
      自定义项让高亮确定性跟随 activeKey，且待办项（不高亮）与导航项共用同一套样式。
    -->
    <el-tooltip content="工作区" placement="right">
      <div class="menu-item" :class="{ 'is-active': activeKey === 'workspace' }" @click="onSelectWorkspace">
        <el-icon><Document /></el-icon>
      </div>
    </el-tooltip>
    <el-tooltip content="Bug 管理" placement="right">
      <div class="menu-item" :class="{ 'is-active': activeKey === 'bug' }" @click="onSelectBug">
        <el-icon><WarningFilled /></el-icon>
      </div>
    </el-tooltip>

    <!-- 待办提醒：覆盖在主 UI 上的抽屉，不改变主 UI 高亮（无 is-active） -->
    <el-tooltip content="待办提醒" placement="right">
      <div class="menu-item" @click="onOpenTodo">
        <el-icon><Bell /></el-icon>
      </div>
    </el-tooltip>

    <div class="spacer" />

    <!-- 底部：设置 -->
    <el-tooltip content="设置" placement="right">
      <div class="menu-item" :class="{ 'is-active': activeKey === 'settings' }" @click="onSelectSettings">
        <el-icon><Setting /></el-icon>
      </div>
    </el-tooltip>
  </el-aside>
</template>

<style scoped>
.nav-col {
  background: #1f2937;
  display: flex;
  flex-direction: column;
  border-right: 1px solid #111827;
  padding-bottom: 8px;
  overflow: hidden; /* 抑制底部横向滚动条：子项溢出不再撑出容器 */
}
.spacer {
  flex: 1;
}
/* 统一导航项样式：折叠态尺寸、hover、is-active（由 activeKey 直接驱动） */
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
/* 选中项高亮：与原 el-menu is-active 视觉一致 */
.menu-item.is-active {
  color: #ffffff;
  background: #409eff;
}
</style>

