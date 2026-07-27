import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import {
  applyImport,
  createRequirement,
  deleteRequirement,
  exportProject,
  getProject,
  listFeatures,
  listIterations,
  listModules,
  pickAndParseImport,
  setRequirementStatus,
  updateRequirement,
} from '@/api'
import type { CreateRequirementInput, UpdateRequirementInput } from '@/api'
import type { Project, ParsedRequirement, RequirementItem, RequirementStatus } from '@/types'
import { useRequirementFilter } from '@/composables/useRequirementFilter'

/** 当前选中的功能（详情页入口）。 */
export interface SelectedFeature {
  module: string
  feature: string
}

export const useRequirementsStore = defineStore('requirements', () => {
  const project = ref<Project | null>(null)
  const modules = ref<string[]>([])

  // 详情页状态
  const selectedFeature = ref<SelectedFeature | null>(null)
  const currentIterations = ref<RequirementItem[]>([])
  const selectedIterationId = ref<string | null>(null)

  const filters = ref({
    dateFrom: '',
    dateTo: '',
    statuses: [] as RequirementStatus[],
    keyword: '',
  })

  const loading = ref(false)
  const error = ref<string | null>(null)

  const selectedIteration = computed(
    () => currentIterations.value.find((it) => it.id === selectedIterationId.value) ?? null,
  )

  // 过滤后的需求（树形用）
  const filteredItems = computed(() => {
    if (!project.value) return [] as RequirementItem[]
    return useRequirementFilter(project.value.items, filters.value)
  })

  async function loadProject(projectId: string) {
    loading.value = true
    error.value = null
    try {
      project.value = await getProject(projectId)
      modules.value = await listModules(projectId)
      // 切换项目时关闭详情
      selectedFeature.value = null
      currentIterations.value = []
      selectedIterationId.value = null
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载项目失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  // ── 详情页 ──

  async function openFeature(module: string, feature: string) {
    if (!project.value) return
    selectedFeature.value = { module, feature }
    await loadIterations(module, feature)
    // 默认选中最新一条
    const iters = currentIterations.value
    selectedIterationId.value = iters.length > 0 ? iters[iters.length - 1].id : null
  }

  async function loadIterations(module: string, feature: string) {
    if (!project.value) return
    currentIterations.value = await listIterations(project.value.id, module, feature)
  }

  function closeFeature() {
    selectedFeature.value = null
    currentIterations.value = []
    selectedIterationId.value = null
  }

  function selectIteration(id: string) {
    selectedIterationId.value = id
  }

  async function createIteration(input: CreateRequirementInput) {
    if (!project.value) return
    const item = await createRequirement(project.value.id, input)
    // 刷新项目与迭代
    await refreshAfterMutation()
    if (selectedFeature.value) {
      await loadIterations(selectedFeature.value.module, selectedFeature.value.feature)
    }
    selectedIterationId.value = item.id
    return item
  }

  async function updateIteration(itemId: string, patch: UpdateRequirementInput) {
    const item = await updateRequirement(itemId, patch)
    await refreshAfterMutation()
    if (selectedFeature.value) {
      await loadIterations(selectedFeature.value.module, selectedFeature.value.feature)
    }
    return item
  }

  async function setIterationStatus(itemId: string, status: RequirementStatus) {
    const item = await setRequirementStatus(itemId, status)
    await refreshAfterMutation()
    if (selectedFeature.value) {
      await loadIterations(selectedFeature.value.module, selectedFeature.value.feature)
    }
    return item
  }

  async function deleteIteration(itemId: string) {
    await deleteRequirement(itemId)
    await refreshAfterMutation()
    if (selectedFeature.value) {
      await loadIterations(selectedFeature.value.module, selectedFeature.value.feature)
      // 若删的是当前选中，重选最新
      const iters = currentIterations.value
      if (!iters.find((it) => it.id === selectedIterationId.value)) {
        selectedIterationId.value = iters.length > 0 ? iters[iters.length - 1].id : null
      }
      // 迭代删空则关闭详情
      if (iters.length === 0) closeFeature()
    }
  }

  async function refreshAfterMutation() {
    if (project.value) {
      project.value = await getProject(project.value.id)
      modules.value = await listModules(project.value.id)
    }
  }

  // ── 导入 / 导出 ──

  async function pickAndImport(): Promise<ParsedRequirement[] | null> {
    return await pickAndParseImport()
  }

  async function apply(requirements: ParsedRequirement[]) {
    if (!project.value) return
    project.value = await applyImport(project.value.id, requirements)
    modules.value = await listModules(project.value.id)
  }

  async function exportCurrent(): Promise<string | null> {
    if (!project.value) return null
    return await exportProject(project.value.id)
  }

  return {
    project,
    modules,
    selectedFeature,
    currentIterations,
    selectedIterationId,
    selectedIteration,
    filters,
    loading,
    error,
    filteredItems,
    loadProject,
    openFeature,
    loadIterations,
    closeFeature,
    selectIteration,
    createIteration,
    updateIteration,
    setIterationStatus,
    deleteIteration,
    pickAndImport,
    apply,
    exportCurrent,
    listFeatures,
  }
})
