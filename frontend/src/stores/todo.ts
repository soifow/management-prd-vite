import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getTodoReminders } from '@/api'
import type { TodoReminder } from '@/types'

/**
 * 待办提醒 store：跨项目聚合未完成需求。
 *
 * 后端单点完成阈值过滤、剩余天数计算与排序，前端仅持有结果并按 bucket 分组渲染。
 */
export const useTodoStore = defineStore('todo', () => {
  const reminders = ref<TodoReminder[]>([])
  const loading = ref(false)
  const loaded = ref(false)

  /** 拉取待办提醒列表（启动 / 刷新 / 跳转后调用）。 */
  async function load() {
    loading.value = true
    try {
      reminders.value = await getTodoReminders()
      loaded.value = true
    } finally {
      loading.value = false
    }
  }

  return {
    reminders,
    loading,
    loaded,
    load,
  }
})
