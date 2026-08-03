import { defineStore } from 'pinia'
import { computed, ref, watch } from 'vue'
import { storeToRefs } from 'pinia'

import { useProjectsStore } from '@/stores/projects'
import {
  createBug,
  deleteBug,
  listBugs,
  listFeatures,
  listIterations,
  listModules,
  resolveBugLink,
  setBugStatus,
  updateBug,
} from '@/api'
import type {
  BugItem,
  BugLevel,
  BugLinkInfo,
  BugStatus,
  CreateBugInput,
  RequirementItem,
  UpdateBugInput,
} from '@/types'
import type { Module } from '@/types/module'
import type { ViewMode } from '@/types/settings'

/** Bug 视图聚合方式（独立于 requirements store 的 viewMode，session 态）。 */
export const useBugsStore = defineStore('bugs', () => {
  const projectsStore = useProjectsStore()
  const { activeProjectId } = storeToRefs(projectsStore)

  const bugs = ref<BugItem[]>([])
  /** 当前项目可用的模块（来自 modules 一等实体表，需求与 bug 共享）。 */
  const modules = ref<Module[]>([])
  const viewMode = ref<ViewMode>('date')

  const filters = ref({
    keyword: '',
    levels: [] as BugLevel[],
    statuses: [] as BugStatus[],
  })

  const selectedBugId = ref<string | null>(null)
  /** 关联迭代解析结果（null=未关联或已失效）。 */
  const linkedInfo = ref<BugLinkInfo | null>(null)
  const loading = ref(false)

  const currentBug = computed(
    () => bugs.value.find((b) => b.id === selectedBugId.value) ?? null,
  )

  /** 应用筛选后的 bug 列表（按级别/状态/关键字）。关键字匹配模块名拼接与内容。 */
  const filteredBugs = computed(() => {
    let list = bugs.value
    if (filters.value.levels.length > 0) {
      list = list.filter((b) => filters.value.levels.includes(b.level))
    }
    if (filters.value.statuses.length > 0) {
      list = list.filter((b) => filters.value.statuses.includes(b.status))
    }
    const kw = filters.value.keyword.trim().toLowerCase()
    if (kw) {
      list = list.filter(
        (b) =>
          b.modules.join(' ').toLowerCase().includes(kw) ||
          b.content.toLowerCase().includes(kw),
      )
    }
    return list
  })

  async function loadBugs(projectId: string, keepSelection = false) {
    loading.value = true
    try {
      bugs.value = await listBugs(projectId)
      modules.value = await listModules(projectId)
      // 默认切换项目时关闭详情；keepSelection=true 时保留当前选中 bug
      if (!keepSelection) {
        selectedBugId.value = null
        linkedInfo.value = null
      }
    } finally {
      loading.value = false
    }
  }

  // 切项目自动加载（与 App.vue 的 requirements watch 并行，互不干扰）
  watch(
    activeProjectId,
    (id) => {
      if (id) {
        void loadBugs(id)
      } else {
        bugs.value = []
        modules.value = []
        selectedBugId.value = null
        linkedInfo.value = null
      }
    },
    { immediate: true },
  )

  function setViewMode(mode: ViewMode) {
    viewMode.value = mode
  }

  /** 打开 bug 详情并解析关联。 */
  async function openBug(id: string) {
    selectedBugId.value = id
    await refreshLinked()
  }

  function closeBug() {
    selectedBugId.value = null
    linkedInfo.value = null
  }

  /** 解析当前 bug 的关联迭代（失效返回 null）。 */
  async function refreshLinked() {
    const b = currentBug.value
    if (!b?.linked_iteration_id) {
      linkedInfo.value = null
      return
    }
    linkedInfo.value = await resolveBugLink(b.linked_iteration_id)
  }

  async function createBugItem(input: CreateBugInput) {
    const b = await createBug(activeProjectId.value!, input)
    await loadBugs(activeProjectId.value!)
    await useProjectsStore().loadSummaries()
    return b
  }

  async function updateBugItem(id: string, patch: UpdateBugInput) {
    const b = await updateBug(id, patch)
    await loadBugs(activeProjectId.value!, true)
    await refreshLinked()
    return b
  }

  async function removeBug(id: string) {
    await deleteBug(id)
    await loadBugs(activeProjectId.value!)
    await useProjectsStore().loadSummaries()
  }

  async function setStatus(id: string, status: BugStatus) {
    const b = await setBugStatus(id, status)
    await loadBugs(activeProjectId.value!)
    return b
  }

  // 关联迭代下拉用：项目级 listFeatures / listIterations（v4 去 module 入参）
  async function listFeaturesFor(): Promise<string[]> {
    if (!activeProjectId.value) return []
    return listFeatures(activeProjectId.value)
  }

  async function listIterationsFor(feature: string): Promise<RequirementItem[]> {
    if (!activeProjectId.value) return []
    return listIterations(activeProjectId.value, feature)
  }

  return {
    bugs,
    modules,
    viewMode,
    filters,
    selectedBugId,
    currentBug,
    linkedInfo,
    loading,
    filteredBugs,
    loadBugs,
    setViewMode,
    openBug,
    closeBug,
    refreshLinked,
    createBugItem,
    updateBugItem,
    removeBug,
    setStatus,
    listFeaturesFor,
    listIterationsFor,
  }
})
