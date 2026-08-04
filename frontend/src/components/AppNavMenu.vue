<script setup lang="ts">
import { computed } from 'vue'
import { storeToRefs } from 'pinia'

import { useTodoStore } from '@/stores/todo'
import {
  IPixelAppWindows,
  IPixelBell,
  IPixelBellOff,
  IPixelDebug,
  IPixelInfoBox,
  IPixelSettings,
} from '@/constants/icons'

defineProps<{ activeKey: 'workspace' | 'settings' | 'bug' }>()
const emit = defineEmits<{
  (e: 'select', key: 'workspace' | 'settings' | 'bug'): void
  (e: 'open-todo'): void
  (e: 'open-about'): void
}>()

// 待办列表非空 -> 亮铃铛；为空 -> 静音铃铛。
// todoStore.reminders 在需求状态/时限/增删变更后由 requirements store 自动刷新，故铃铛实时反映。
const todoStore = useTodoStore()
const { reminders } = storeToRefs(todoStore)
const hasReminders = computed(() => reminders.value.length > 0)

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
function onOpenAbout() {
  emit('open-about')
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
        <el-icon><IPixelAppWindows /></el-icon>
      </div>
    </el-tooltip>
    <el-tooltip content="Bug 管理" placement="right">
      <div class="menu-item" :class="{ 'is-active': activeKey === 'bug' }" @click="onSelectBug">
        <el-icon><IPixelDebug /></el-icon>
      </div>
    </el-tooltip>

    <!-- 待办提醒：覆盖在主 UI 上的抽屉，不改变主 UI 高亮（无 is-active）。
         铃铛按待办列表是否为空切换 bell/bell-off，实时反映「有待办」状态。 -->
    <el-tooltip content="待办提醒" placement="right">
      <div class="menu-item" @click="onOpenTodo">
        <el-icon>
          <IPixelBell v-if="hasReminders" />
          <IPixelBellOff v-else />
        </el-icon>
      </div>
    </el-tooltip>

    <div class="spacer" />

    <!-- 底部：信息（项目简介弹窗，非视图，不高亮） -->
    <el-tooltip content="关于" placement="right">
      <div class="menu-item" @click="onOpenAbout">
        <el-icon><IPixelInfoBox /></el-icon>
      </div>
    </el-tooltip>

    <!-- 底部：设置 -->
    <el-tooltip content="设置" placement="right">
      <div class="menu-item" :class="{ 'is-active': activeKey === 'settings' }" @click="onSelectSettings">
        <el-icon><IPixelSettings /></el-icon>
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
  width: 64px;
  display: flex; /* flex 居中，避免 el-icon(inline-flex) baseline 对齐导致图标偏上 */
  align-items: center;
  justify-content: center;
  cursor: pointer;
}
/* 菜单栏宽度 64px 不变，单独放大图标以提升可点击感与可读性 */
.menu-item :deep(.el-icon) {
  font-size: 24px;
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
