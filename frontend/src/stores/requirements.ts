import { defineStore } from 'pinia'
import { computed, ref } from 'vue'

import { useProjectsStore } from '@/stores/projects'
import { useTodoStore } from '@/stores/todo'

import {
  applyFullImport,
  createRequirement,
  createSubitem,
  deleteRequirement,
  deleteSubitem,
  exportProjectMd,
  getProject,
  listFeatures,
  listIterations,
  listModules,
  listSubitems,
  listSubitemProgress,
  parseMdImport,
  pickSmartImportFile as pickSmartImportFileApi,
  runSmartImport as runSmartImportApi,
  setRequirementStatus,
  setSubitemStatus,
  updateRequirement,
  updateSubitem,
} from '@/api'
import type { CreateRequirementInput, UpdateRequirementInput } from '@/api'
import type {
  ImportTarget,
  ParseMdResult,
  Project,
  ParsedProject,
  RequirementItem,
  RequirementStatus,
  RequirementSubitem,
  SmartPickResult,
  SmartRunResult,
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
   * 各 feature 的子需求进度摘要缓存（{projectId}\x00{feature} -> {done,total}）。
   * 键带 projectId 前缀避免跨项目同名 feature 串号。项目加载时由后端批量聚合填充，
   * 子需求/迭代/导入变更后增量重查。视图层经 `currentProgressMap` 取当前项目数据。
   */
  const featureProgressMap = ref<Record<string, { done: number; total: number }>>({})

  /** 组装 featureProgressMap 的键（projectId 隔离，feature 名不应含 \x00）。 */
  function progressKey(projectId: string, feature: string): string {
    return `${projectId}\x00${feature}`
  }

  /** 拉取当前项目各 feature 子需求进度并合并进缓存（保留其他项目旧缓存）。失败静默。 */
  async function loadSubitemProgress() {
    if (!project.value) return
    try {
      const map = await listSubitemProgress(project.value.id)
      const prefix = progressKey(project.value.id, '')
      const next: Record<string, { done: number; total: number }> = {}
      for (const [k, v] of Object.entries(featureProgressMap.value)) {
        if (!k.startsWith(prefix)) next[k] = v
      }
      for (const [feat, prog] of Object.entries(map)) {
        next[progressKey(project.value.id, feat)] = prog
      }
      featureProgressMap.value = next
    } catch {
      // 进度为次要展示数据，失败不阻断主流程
    }
  }

  /** 当前项目的子需求进度（键为 feature，供视图直接按 feature 查询）。 */
  const currentProgressMap = computed<Record<string, { done: number; total: number }>>(() => {
    if (!project.value) return {}
    const prefix = progressKey(project.value.id, '')
    const out: Record<string, { done: number; total: number }> = {}
    for (const [k, v] of Object.entries(featureProgressMap.value)) {
      if (k.startsWith(prefix)) out[k.slice(prefix.length)] = v
    }
    return out
  })

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
      // 批量拉取子需求进度（fire-and-forget，不阻塞主流程）
      void loadSubitemProgress()
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
    featureProgressMap.value = {}
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
    void loadSubitemProgress()
    refreshTodo()
    return sub
  }

  async function patchSubitem(subitemId: string, patch: Parameters<typeof updateSubitem>[1]) {
    const sub = await updateSubitem(subitemId, patch)
    const itId = selectedIterationId.value
    if (itId) await loadSubitems(itId)
    void loadSubitemProgress()
    refreshTodo()
    return sub
  }

  async function setSubitemStatusItem(subitemId: string, status: RequirementStatus) {
    const sub = await setSubitemStatus(subitemId, status)
    const itId = selectedIterationId.value
    if (itId) await loadSubitems(itId)
    void loadSubitemProgress()
    refreshTodo()
    return sub
  }

  async function removeSubitem(subitemId: string) {
    await deleteSubitem(subitemId)
    const itId = selectedIterationId.value
    if (itId) await loadSubitems(itId)
    void loadSubitemProgress()
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
      // 迭代变更可能级联影响子需求进度（如删迭代级联删子需求、改 feature 归属）
      void loadSubitemProgress()
    }
  }

  // ── 导入 / 导出 ──

  /** 弹 .md 文件框并解析为 ParsedProject，用于导入预览。取消返回 null。 */
  async function parseImport(): Promise<ParseMdResult | null> {
    return await parseMdImport()
  }

  /** 智能导入是否进行中（①→②→③ 全程 true，关弹窗复位）。侧边栏按钮据此 :loading 防重入，
   *  由 SmartImportDialog 在 open/close 置位。 */
  const smartImporting = ref(false)

  /** 智能导入第①步：弹文件框 -> 读文本 -> 校验长度。取消返回 null。 */
  async function pickSmartImportFile(): Promise<SmartPickResult | null> {
    return await pickSmartImportFileApi()
  }

  /** 智能导入第②步：调 LLM 结构化 -> ParsedProject（预览用）。 */
  async function runSmartImport(text: string, filename: string): Promise<SmartRunResult> {
    return await runSmartImportApi(text, filename)
  }

  /** 应用完整导入到目标项目（基础导入 target=project_id 或新建 name；reuse_id 由 parsed 携带）。 */
  async function applyFullImportTo(target: ImportTarget, parsed: ParsedProject) {
    const p = await applyFullImport(target, parsed)
    // 无论导入到当前项目还是新建，刷新项目列表以反映最新汇总/排序
    await useProjectsStore().loadSummaries()
    // 若导入目标为当前项目，就地刷新其数据与模块；否则由调用方选中新项目后触发 loadProject
    if (target.project_id && project.value?.id === target.project_id) {
      project.value = p
      modules.value = await listModules(project.value.id)
      void loadSubitemProgress()
    }
    refreshTodo()
    return p
  }

  /** 导出当前项目为 .md 双轨格式（弹保存对话框）。 */
  async function exportCurrent(includeBug = true): Promise<string | null> {
    if (!project.value) return null
    return await exportProjectMd(project.value.id, includeBug)
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
    currentProgressMap,
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
    parseImport,
    applyFullImportTo,
    smartImporting,
    pickSmartImportFile,
    runSmartImport,
    exportCurrent,
    listFeatures,
  }
})
