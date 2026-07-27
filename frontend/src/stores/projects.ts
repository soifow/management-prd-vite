import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  createProject,
  deleteProject,
  listProjects,
  renameProject,
} from '@/api'
import type { ProjectSummary } from '@/types'

export const useProjectsStore = defineStore('projects', () => {
  const summaries = ref<ProjectSummary[]>([])
  const activeProjectId = ref<string | null>(null)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const activeProject = computed(() =>
    summaries.value.find((p) => p.id === activeProjectId.value),
  )

  async function loadSummaries() {
    loading.value = true
    error.value = null
    try {
      summaries.value = await listProjects()
      if (summaries.value.length > 0 && !activeProjectId.value) {
        activeProjectId.value = summaries.value[0].id
      }
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载项目失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  async function create(name: string) {
    const summary = await createProject(name)
    summaries.value.push(summary)
    activeProjectId.value = summary.id
    return summary
  }

  async function rename(projectId: string, name: string) {
    const summary = await renameProject(projectId, name)
    const idx = summaries.value.findIndex((p) => p.id === projectId)
    if (idx >= 0) summaries.value[idx] = summary
    return summary
  }

  async function remove(projectId: string) {
    await deleteProject(projectId)
    summaries.value = summaries.value.filter((p) => p.id !== projectId)
    if (activeProjectId.value === projectId) {
      activeProjectId.value = summaries.value[0]?.id ?? null
    }
  }

  function select(projectId: string) {
    activeProjectId.value = projectId
  }

  return {
    summaries,
    activeProjectId,
    activeProject,
    loading,
    error,
    loadSummaries,
    create,
    rename,
    remove,
    select,
  }
})
