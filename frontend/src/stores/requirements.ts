import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useProjectsStore } from '@/stores/projects'
import { useTodoStore } from '@/stores/todo'

import {
  applyImport,
  applyImportAsNewProject,
  createRequirement,
  createSubitem,
  deleteRequirement,
  deleteSubitem,
  exportProject,
  getProject,
  listFeatures,
  listIterations,
  listModules,
  listSubitems,
  pickAndParseImport,
  setRequirementStatus,
  setSubitemStatus,
  updateRequirement,
  updateSubitem,
} from '@/api'
import type { CreateRequirementInput, UpdateRequirementInput } from '@/api'
import type {
  Project,
  ParsedRequirement,
  PickParseResult,
  RequirementItem,
  RequirementStatus,
  RequirementSubitem,
} from '@/types'
import type { Module } from '@/types/module'
import type { ViewMode } from '@/types/settings'
import { useRequirementFilter } from '@/composables/useRequirementFilter'

/** 当前选中的功能（详情页入口）。v4：迭代链键解耦 module 后不再含 module。 */
export interface SelectedFeature {
  feature: string
}

export const useRequirementsStore = defineStore('requirements', () => {
  const project = ref<Project | null>(null)
  const modules = ref<Module[]>([])

  // 聚合视图方式（session 态；启动时由 App.vue 用 settings.defaultViewMode 初始化）
  const viewMode = ref<ViewMode>('date')

  function setViewMode(mode: ViewMode) {
    viewMode.value = mode
  }

  // 详情页状态
  const selectedFeature = ref<SelectedFeature | null>(null)
  const currentIterations = ref<RequirementItem[]>([])
  const selectedIterationId = ref<string | null>(null)
  // 迭代级子需求（当前选中迭代的子需求清单）
  const currentSubitems = ref<RequirementSubitem[]>([])
  const subitemsLoading = ref(false)
  /**
   * 各 feature 的子需求进度摘要缓存（feature -> {done,total}）。
   * 仅当设置项 `show_subitem_progress_in_tree` 开启时树形功能节点据此显示 (done/total)；
   * 进度在 FeatureDetail 打开该 feature 时回填，避免树渲染批量查询。
   */
  const featureProgressMap = ref<Record<string, { done: number; total: number }>>({})

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
      currentSubitems.value = []
    } catch (e) {
      error.value = e instanceof Error ? e.message : '加载项目失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  // ── 详情页 ──

  async function openFeature(feature: string) {
    if (!project.value) return
    selectedFeature.value = { feature }
    await loadIterations(feature)
    // 默认选中最新一条并加载其子需求
    const iters = currentIterations.value
    selectedIterationId.value = iters.length > 0 ? iters[iters.length - 1].id : null
    await loadSubitems(selectedIterationId.value)
  }

  async function loadIterations(feature: string) {
    if (!project.value) return
    currentIterations.value = await listIterations(project.value.id, feature)
  }

  function closeFeature() {
    selectedFeature.value = null
    currentIterations.value = []
    selectedIterationId.value = null
    currentSubitems.value = []
  }

  /** 完成提示守卫：切换迭代时重置（见 selectIteration）；本次停留在该迭代期间只弹一次。 */
  const completionPromptGuard = ref(false)

  /** 清空当前项目数据与详情状态（项目被删除/无选中项目时调用）。 */
  function reset() {
    project.value = null
    modules.value = []
    closeFeature()
  }

  async function selectIteration(id: string) {
    selectedIterationId.value = id
    completionPromptGuard.value = false
    await loadSubitems(id)
  }

  // ── 子需求 ──

  async function loadSubitems(iterationId: string | null) {
    if (!iterationId) {
      currentSubitems.value = []
      return
    }
    subitemsLoading.value = true
    try {
      currentSubitems.value = await listSubitems(iterationId)
      // 回填 feature 子需求进度摘要（供树形节点显示）
      const feat = selectedFeature.value?.feature
      if (feat && currentIterations.value.length > 0) {
        // 聚合该 feature 所有迭代的子需求总数。简化：只缓存当前迭代的子需求数。
        const total = currentSubitems.value.length
        const done = currentSubitems.value.filter((s) => s.status === 'done').length
        if (total > 0) {
          featureProgressMap.value = { ...featureProgressMap.value, [feat]: { done, total } }
        }
      }
    } finally {
      subitemsLoading.value = false
    }
  }

  async function addSubitem(
    iterationId: string,
    content: string,
    status: RequirementStatus,
    completionDeadline?: string | null,
  ) {
    const sub = await createSubitem(iterationId, {
      iteration_id: iterationId,
      content,
      status,
      completion_deadline: completionDeadline ?? undefined,
    })
    await loadSubitems(iterationId)
    refreshTodo()
    return sub
  }

  async function patchSubitem(subitemId: string, patch: Parameters<typeof updateSubitem>[1]) {
    const sub = await updateSubitem(subitemId, patch)
    const itId = selectedIterationId.value
    if (itId) await loadSubitems(itId)
    refreshTodo()
    return sub
  }

  async function setSubitemStatusItem(subitemId: string, status: RequirementStatus) {
    const sub = await setSubitemStatus(subitemId, status)
    const itId = selectedIterationId.value
    if (itId) await loadSubitems(itId)
    refreshTodo()
    return sub
  }

  async function removeSubitem(subitemId: string) {
    await deleteSubitem(subitemId)
    const itId = selectedIterationId.value
    if (itId) await loadSubitems(itId)
    refreshTodo()
  }

  async function createIteration(input: CreateRequirementInput) {
    if (!project.value) return
    const item = await createRequirement(project.value.id, input)
    // 刷新项目与迭代
    await refreshAfterMutation()
    if (selectedFeature.value) {
      await loadIterations(selectedFeature.value.feature)
    }
    selectedIterationId.value = item.id
    await loadSubitems(item.id)
    refreshTodo()
    return item
  }

  async function updateIteration(itemId: string, patch: UpdateRequirementInput) {
    const item = await updateRequirement(itemId, patch)
    await refreshAfterMutation()
    if (selectedFeature.value) {
      // feature 被改时，迭代迁到新分组下：同步 selectedFeature 并按新 feature 重新加载，
      // 否则仍用旧值查询会拿不到已迁移的迭代（当前详情变空）
      const nextFeature = patch.feature ?? selectedFeature.value.feature
      if (nextFeature !== selectedFeature.value.feature) {
        selectedFeature.value = { feature: nextFeature }
      }
      await loadIterations(selectedFeature.value.feature)
      // 当前选中迭代若仍存在，重新加载其子需求（modules 已回填）
      if (selectedIterationId.value) await loadSubitems(selectedIterationId.value)
    }
    refreshTodo()
    return item
  }

  async function setIterationStatus(itemId: string, status: RequirementStatus) {
    const item = await setRequirementStatus(itemId, status)
    await refreshAfterMutation()
    if (selectedFeature.value) {
      await loadIterations(selectedFeature.value.feature)
    }
    refreshTodo()
    return item
  }

  async function deleteIteration(itemId: string) {
    await deleteRequirement(itemId)
    await refreshAfterMutation()
    if (selectedFeature.value) {
      await loadIterations(selectedFeature.value.feature)
      // 若删的是当前选中，重选最新
      const iters = currentIterations.value
      if (!iters.find((it) => it.id === selectedIterationId.value)) {
        selectedIterationId.value = iters.length > 0 ? iters[iters.length - 1].id : null
      }
      await loadSubitems(selectedIterationId.value)
      // 迭代删空则关闭详情
      if (iters.length === 0) closeFeature()
    }
    refreshTodo()
  }

  /** 需求状态/时限/增删变化后刷新跨项目待办列表（fire-and-forget，不阻塞 UI）。
   *  待办列表是否为空驱动主菜单铃铛 bell/bell-off 切换，故需实时同步。 */
  function refreshTodo() {
    void useTodoStore().load()
  }

  async function refreshAfterMutation() {
    if (project.value) {
      project.value = await getProject(project.value.id)
      modules.value = await listModules(project.value.id)
      // 同步刷新侧边栏项目汇总：需求的增删改会影响 list_date / requirement_count / 排序
      await useProjectsStore().loadSummaries()
    }
  }

  // ── 导入 / 导出 ──

  async function pickAndImport(): Promise<PickParseResult | null> {
    return await pickAndParseImport()
  }

  async function apply(requirements: ParsedRequirement[]) {
    if (!project.value) return
    project.value = await applyImport(project.value.id, requirements)
    modules.value = await listModules(project.value.id)
    await useProjectsStore().loadSummaries()
    refreshTodo()
  }

  /** 新建项目并将导入需求写入，返回新建的项目（后续由调用方刷新并选中）。 */
  async function applyAsNewProject(name: string, requirements: ParsedRequirement[]): Promise<Project> {
    const p = await applyImportAsNewProject(name, requirements)
    refreshTodo()
    return p
  }

  async function exportCurrent(): Promise<string | null> {
    if (!project.value) return null
    return await exportProject(project.value.id)
  }

  return {
    project,
    modules,
    viewMode,
    selectedFeature,
    currentIterations,
    selectedIterationId,
    selectedIteration,
    currentSubitems,
    subitemsLoading,
    featureProgressMap,
    filters,
    loading,
    error,
    filteredItems,
    loadProject,
    openFeature,
    loadIterations,
    closeFeature,
    reset,
    selectIteration,
    setViewMode,
    completionPromptGuard,
    createIteration,
    updateIteration,
    setIterationStatus,
    deleteIteration,
    loadSubitems,
    addSubitem,
    patchSubitem,
    setSubitemStatusItem,
    removeSubitem,
    pickAndImport,
    apply,
    applyAsNewProject,
    exportCurrent,
    listFeatures,
  }
})
