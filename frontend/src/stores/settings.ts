import { defineStore } from 'pinia'
import { ref } from 'vue'

import { getStorageInfo, migrateStorage, pickStorageDir } from '@/api'
import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import type { StorageInfo } from '@/types/api'

export const useSettingsStore = defineStore('settings', () => {
  const storageInfo = ref<StorageInfo | null>(null)
  const loading = ref(false)

  async function loadStorageInfo() {
    loading.value = true
    try {
      storageInfo.value = await getStorageInfo()
    } finally {
      loading.value = false
    }
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
    loadStorageInfo,
    pickFolder,
    migrate,
  }
})
