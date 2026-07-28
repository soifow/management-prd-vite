import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getSettings, getStorageInfo, migrateStorage, pickStorageDir, updateSettings } from '@/api'
import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import type { StorageInfo } from '@/types/api'
import type { ViewMode } from '@/types/settings'

export const useSettingsStore = defineStore('settings', () => {
  const storageInfo = ref<StorageInfo | null>(null)
  const loading = ref(false)

  // 应用设置（落盘在 storage_dir/settings.json）
  const defaultViewMode = ref<ViewMode>('date')

  async function loadStorageInfo() {
    loading.value = true
    try {
      storageInfo.value = await getStorageInfo()
    } finally {
      loading.value = false
    }
  }

  /** 加载应用设置（启动时调用，初始化 defaultViewMode）。 */
  async function loadSettings() {
    const settings = await getSettings()
    defaultViewMode.value = settings.default_view_mode
  }

  /** 修改默认聚合方式并落盘。 */
  async function saveDefaultViewMode(mode: ViewMode) {
    const settings = await updateSettings({ default_view_mode: mode })
    defaultViewMode.value = settings.default_view_mode
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
    loadStorageInfo,
    loadSettings,
    saveDefaultViewMode,
    pickFolder,
    migrate,
  }
})
