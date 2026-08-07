import { defineStore } from 'pinia'
import { ref } from 'vue'

import {
  deleteImportBackup,
  getSettings,
  getStorageInfo,
  listImportBackups,
  migrateStorage,
  pickStorageDir,
  restoreImportBackup,
  updateSettings,
} from '@/api'
import { useProjectsStore } from '@/stores/projects'
import { useRequirementsStore } from '@/stores/requirements'
import type { ImportBackupEntry, StorageInfo } from '@/types/api'
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
  // 待办提醒：紧急阈值（剩余天数≤该值的聚合标题栏用紧急警告色）
  const urgentThresholdDays = ref(3)
  // 待办提醒：当前提醒阈值内聚合标题栏警告色（橙）
  const reminderWarningColor = ref('#eb9f24')
  // 待办提醒：紧急阈值内聚合标题栏警告色（深红）
  const urgentWarningColor = ref('#dc2626')
  // 待办提醒：无时限需求是否常驻待办列表
  const showNoDeadlineInTodo = ref(true)
  // 功能节点是否显示子需求进度 (done/total)（树形 + 时间聚合视图）
  const showSubitemProgressInTree = ref(false)
  // LLM 智能导入配置
  const llmEnabled = ref(false)
  const llmBaseUrl = ref('')
  const llmApiKey = ref('')
  const llmModel = ref('')
  const llmTimeout = ref(120)
  // 导入备份自动清理保留数量
  const backupRetentionCount = ref(10)
  // 需求侧默认是否隐藏仅存 bug 的项目（仅作冷启动时工作区「需求/全部」开关的默认值）
  const hideBugOnlyProjects = ref(false)
  // 功能名显示截断长度（超出加省略号；0=不截断）
  const featureNameMaxLength = ref(12)
  // 应用设置是否已从后端加载完成：启动时序标志，供 ProjectSidebar 等组件在 loadSettings
  // 落定后取一次设置默认值再脱钩（与会话内临时切换互不影响）。
  const settingsLoaded = ref(false)
  // 导入前备份清单（最新在前）
  const importBackups = ref<ImportBackupEntry[]>([])

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
        : ['storage', 'display', 'reminder', 'subitem', 'llm', 'backup']
    reminderThresholdDays.value = settings.reminder_threshold_days
    urgentThresholdDays.value = settings.urgent_threshold_days
    reminderWarningColor.value = settings.reminder_warning_color
    urgentWarningColor.value = settings.urgent_warning_color
    showNoDeadlineInTodo.value = settings.show_no_deadline_in_todo
    showSubitemProgressInTree.value = settings.show_subitem_progress_in_tree
    llmEnabled.value = settings.llm_enabled
    llmBaseUrl.value = settings.llm_base_url
    llmApiKey.value = settings.llm_api_key
    llmModel.value = settings.llm_model
    llmTimeout.value = settings.llm_timeout
    backupRetentionCount.value = settings.backup_retention_count
    hideBugOnlyProjects.value = settings.hide_bug_only_projects
    featureNameMaxLength.value = settings.feature_name_max_length
    settingsLoaded.value = true
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

  /** 修改待办提醒设置并落盘（阈值 + 紧急阈值 + 警告色 + 无时限常驻开关）。 */
  async function saveReminderSettings(
    threshold: number,
    urgentThreshold: number,
    reminderColor: string,
    urgentColor: string,
    showNoDeadline: boolean,
  ) {
    const settings = await updateSettings({
      reminder_threshold_days: threshold,
      urgent_threshold_days: urgentThreshold,
      reminder_warning_color: reminderColor,
      urgent_warning_color: urgentColor,
      show_no_deadline_in_todo: showNoDeadline,
    })
    reminderThresholdDays.value = settings.reminder_threshold_days
    urgentThresholdDays.value = settings.urgent_threshold_days
    reminderWarningColor.value = settings.reminder_warning_color
    urgentWarningColor.value = settings.urgent_warning_color
    showNoDeadlineInTodo.value = settings.show_no_deadline_in_todo
  }

  /** 修改「功能节点显示子需求进度」开关并落盘。 */
  async function saveSubitemProgressInTree(show: boolean) {
    const settings = await updateSettings({ show_subitem_progress_in_tree: show })
    showSubitemProgressInTree.value = settings.show_subitem_progress_in_tree
  }

  /** 修改 LLM 智能导入配置并落盘。 */
  async function saveLlmConfig(config: {
    enabled: boolean
    baseUrl: string
    apiKey: string
    model: string
    timeout: number
  }) {
    const settings = await updateSettings({
      llm_enabled: config.enabled,
      llm_base_url: config.baseUrl,
      llm_api_key: config.apiKey,
      llm_model: config.model,
      llm_timeout: config.timeout,
    })
    llmEnabled.value = settings.llm_enabled
    llmBaseUrl.value = settings.llm_base_url
    llmApiKey.value = settings.llm_api_key
    llmModel.value = settings.llm_model
    llmTimeout.value = settings.llm_timeout
  }

  // ── 导入前备份与回滚 ──

  /** 修改导入备份保留数量并落盘。 */
  async function saveBackupRetentionCount(count: number) {
    const settings = await updateSettings({ backup_retention_count: count })
    backupRetentionCount.value = settings.backup_retention_count
  }

  /**
   * 修改「需求侧默认隐藏仅 bug 项目」并落盘。
   * 该值仅作为下次冷启动时工作区「需求/全部」开关的默认值，与会话内当前开关值相互独立
   * （与默认聚合方式 defaultViewMode 语义一致）；故此处仅落盘，不重置当前侧边栏过滤状态。
   */
  async function saveHideBugOnlyProjects(hide: boolean) {
    const settings = await updateSettings({ hide_bug_only_projects: hide })
    hideBugOnlyProjects.value = settings.hide_bug_only_projects
  }

  /** 修改功能名截断长度并落盘。该值仅影响功能名显示，不回流已存储数据。 */
  async function saveFeatureNameMaxLength(length: number) {
    const settings = await updateSettings({ feature_name_max_length: length })
    featureNameMaxLength.value = settings.feature_name_max_length
  }

  /** 加载导入前备份清单（最新在前）。 */
  async function loadImportBackups() {
    importBackups.value = await listImportBackups()
  }

  /**
   * 回滚到指定导入前备份点。回滚后数据库已被覆盖，需全量刷新前端数据视图：
   * 项目列表 + 当前项目（当前项目回滚后可能已不存在，缺失则重置）+ 备份清单。
   */
  async function restoreImportBackupById(id: string) {
    await restoreImportBackup(id)
    const projectsStore = useProjectsStore()
    const requirementsStore = useRequirementsStore()
    await projectsStore.loadSummaries()
    const activeId = projectsStore.activeProjectId
    if (activeId && projectsStore.summaries.some((p) => p.id === activeId)) {
      await requirementsStore.loadProject(activeId)
    } else {
      requirementsStore.reset()
    }
    await loadImportBackups()
  }

  /** 删除单个导入备份并刷新清单。 */
  async function deleteImportBackupById(id: string) {
    await deleteImportBackup(id)
    await loadImportBackups()
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
    urgentThresholdDays,
    reminderWarningColor,
    urgentWarningColor,
    showNoDeadlineInTodo,
    showSubitemProgressInTree,
    llmEnabled,
    llmBaseUrl,
    llmApiKey,
    llmModel,
    llmTimeout,
    backupRetentionCount,
    hideBugOnlyProjects,
    featureNameMaxLength,
    settingsLoaded,
    importBackups,
    loadStorageInfo,
    loadSettings,
    saveDefaultViewMode,
    saveProjectListDateMode,
    saveSettingsOrder,
    saveReminderSettings,
    saveSubitemProgressInTree,
    saveLlmConfig,
    saveBackupRetentionCount,
    saveHideBugOnlyProjects,
    saveFeatureNameMaxLength,
    loadImportBackups,
    restoreImportBackupById,
    deleteImportBackupById,
    pickFolder,
    migrate,
  }
})
