import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getSettings, getStorageInfo, migrateStorage, pickStorageDir, updateSettings } from '@/api'
import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import type { StorageInfo } from '@/types/api'
import type { ProjectListDateMode, ViewMode } from '@/types/settings'

export const useSettingsStore = defineStore('settings', () => {
  const storageInfo = ref<StorageInfo | null>(null)
  const loading = ref(false)

  // 应用设置（落盘在 storage_dir/settings.json）
  const defaultViewMode = ref<ViewMode>('date')
  // 项目列表「最新」日期口径（落盘 settings.json）
  const projectListDateMode = ref<ProjectListDateMode>('latest_any')
  // 设置页分组 tab 的显示顺序（落盘 settings.json）
  const settingsOrder = ref<string[]>(['storage', 'display'])
  // 待办提醒：剩余天数阈值（含逾期）
  const reminderThresholdDays = ref(7)
  // 待办提醒：无时限需求是否常驻待办列表
  const showNoDeadlineInTodo = ref(true)

  async function loadStorageInfo() {
    loading.value = true
    try {
      storageInfo.value = await getStorageInfo()
    } finally {
      loading.value = false
    }
  }

  /** 加载应用设置（启动时调用，初始化 defaultViewMode 与 settingsOrder）。 */
  async function loadSettings() {
    const settings = await getSettings()
    defaultViewMode.value = settings.default_view_mode
    projectListDateMode.value = settings.project_list_date_mode
    settingsOrder.value =
      settings.settings_order && settings.settings_order.length > 0
        ? settings.settings_order
        : ['storage', 'display']
    reminderThresholdDays.value = settings.reminder_threshold_days
    showNoDeadlineInTodo.value = settings.show_no_deadline_in_todo
  }

  /** 修改默认聚合方式并落盘。 */
  async function saveDefaultViewMode(mode: ViewMode) {
    const settings = await updateSettings({ default_view_mode: mode })
    defaultViewMode.value = settings.default_view_mode
  }

  /**
   * 修改项目列表日期口径并落盘，随后重载侧边栏项目汇总。
   * 口径改变后 list_projects 返回的 list_date/排序随之变化，故需立即刷新侧边栏。
   */
  async function saveProjectListDateMode(mode: ProjectListDateMode) {
    const settings = await updateSettings({ project_list_date_mode: mode })
    projectListDateMode.value = settings.project_list_date_mode
    await useProjectsStore().loadSummaries()
  }

  /** 修改设置分组顺序并落盘。 */
  async function saveSettingsOrder(order: string[]) {
    const settings = await updateSettings({ settings_order: order })
    settingsOrder.value = settings.settings_order
  }

  /** 修改待办提醒设置并落盘（阈值 + 无时限常驻开关）。 */
  async function saveReminderSettings(threshold: number, showNoDeadline: boolean) {
    const settings = await updateSettings({
      reminder_threshold_days: threshold,
      show_no_deadline_in_todo: showNoDeadline,
    })
    reminderThresholdDays.value = settings.reminder_threshold_days
    showNoDeadlineInTodo.value = settings.show_no_deadline_in_todo
  }

  /** 弹文件夹选择框，返回所选路径或 null（取消）。 */
  async function pickFolder(): Promise<string | null> {
    return await pickStorageDir()
  }

  /**
   * 迁移存储目录到新位置，并刷新前端数据视图。
   * 迁移成功后，后端已重载数据，前端需重新拉取项目列表与当前项目。
   */
  async function migrate(newDir: string) {
    storageInfo.value = await migrateStorage(newDir)

    // 后端已重载数据，刷新前端视图
    const projectsStore = useProjectsStore()
    const requirementsStore = useRequirementsStore()
    await projectsStore.loadSummaries()
    const activeId = projectsStore.activeProjectId
    if (activeId) {
      await requirementsStore.loadProject(activeId)
    } else {
      requirementsStore.reset()
    }
  }

  return {
    storageInfo,
    loading,
    defaultViewMode,
    projectListDateMode,
    settingsOrder,
    reminderThresholdDays,
    showNoDeadlineInTodo,
    loadStorageInfo,
    loadSettings,
    saveDefaultViewMode,
    saveProjectListDateMode,
    saveSettingsOrder,
    saveReminderSettings,
    pickFolder,
    migrate,
  }
})
