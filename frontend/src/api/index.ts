/**
 * 后端 WebApi 的 TypeScript 封装层。
 */

import { isApiErrorEnvelope } from '@/types/api'
import type { ImportBackupEntry, StorageInfo } from '@/types/api'
import type {
  BugItem,
  BugLinkInfo,
  BugStatus,
  CreateBugInput,
  UpdateBugInput,
} from '@/types/bug'
import type {
  ImportTarget,
  ParseMdResult,
  ParsedProject,
  SmartPickResult,
  SmartRunResult,
} from '@/types/import'
import type { Module } from '@/types/module'
import type { Project, ProjectSummary } from '@/types/project'
import type { RequirementItem, RequirementStatus } from '@/types/requirement'
import type { AppSettings } from '@/types/settings'
import type {
  CreateSubitemInput,
  RequirementSubitem,
  UpdateSubitemInput,
} from '@/types/subitem'
import type { TodoReminder } from '@/types/todo'

/** 后端错误信封抛出的统一异常类型。 */
export class ApiError extends Error {
  constructor(message: string) {
    super(message)
    this.name = 'ApiError'
  }
}

let readyPromise: Promise<void> | null = null

/** 等待 PyWebView 桥接就绪。 */
export function whenReady(): Promise<void> {
  if (window.pywebview?.api) {
    return Promise.resolve()
  }
  if (!readyPromise) {
    readyPromise = new Promise<void>((resolve) => {
      window.addEventListener('pywebviewready', () => resolve(), { once: true })
    })
  }
  return readyPromise
}

/** 获取已就绪的桥接对象，未就绪时抛 ApiError。 */
function bridge() {
  const api = window.pywebview?.api
  if (!api) {
    throw new ApiError('后端桥接未就绪，请通过桌面应用启动')
  }
  return api
}

/** 调用桥接方法并解包错误信封。 */
async function invoke<T>(fn: () => Promise<unknown>): Promise<T> {
  try {
    const result = await fn()
    if (isApiErrorEnvelope(result)) {
      throw new ApiError(result.error)
    }
    return result as T
  } catch (e) {
    if (e instanceof ApiError) throw e
    throw new ApiError(e instanceof Error ? e.message : String(e))
  }
}

// ── 项目 ────────────────────────────────────────────────────

export const listProjects = (): Promise<ProjectSummary[]> => invoke(() => bridge().list_projects())

export const getProject = (projectId: string): Promise<Project> =>
  invoke(() => bridge().get_project(projectId))

export const createProject = (name: string): Promise<ProjectSummary> =>
  invoke(() => bridge().create_project(name))

export const renameProject = (projectId: string, name: string): Promise<ProjectSummary> =>
  invoke(() => bridge().rename_project(projectId, name))

export const deleteProject = (projectId: string): Promise<boolean> =>
  invoke(() => bridge().delete_project(projectId))

export const listModules = (projectId: string): Promise<Module[]> =>
  invoke(() => bridge().list_modules(projectId))

export const createModule = (projectId: string, name: string): Promise<Module> =>
  invoke(() => bridge().create_module(projectId, name))

export const deleteModule = (moduleId: string): Promise<boolean> =>
  invoke(() => bridge().delete_module(moduleId))

export const listFeatures = (projectId: string): Promise<string[]> =>
  invoke(() => bridge().list_features(projectId))

export const listIterations = (
  projectId: string,
  feature: string,
): Promise<RequirementItem[]> => invoke(() => bridge().list_iterations(projectId, feature))

// ── 需求 ────────────────────────────────────────────────────

export interface CreateRequirementInput {
  module_names: string[]
  feature: string
  content: string
  status: RequirementStatus
  date: string
  completion_deadline: string | null
}

export interface UpdateRequirementInput {
  module_names?: string[]
  feature?: string
  content?: string
  status?: RequirementStatus
  date?: string
  /** ISO yyyy-MM-dd（传入则设为该日期） */
  completion_deadline?: string
  /** true 则置 NULL（优先级高于 completion_deadline） */
  clear_completion_deadline?: boolean
}

export const createRequirement = (
  projectId: string,
  input: CreateRequirementInput,
): Promise<RequirementItem> => invoke(() => bridge().create_requirement(projectId, input))

export const updateRequirement = (
  itemId: string,
  patch: UpdateRequirementInput,
): Promise<RequirementItem> => invoke(() => bridge().update_requirement(itemId, patch))

export const setRequirementStatus = (
  itemId: string,
  status: RequirementStatus,
): Promise<RequirementItem> => invoke(() => bridge().set_requirement_status(itemId, status))

export const deleteRequirement = (itemId: string): Promise<boolean> =>
  invoke(() => bridge().delete_requirement(itemId))

// ── 迭代级子需求 ────────────────────────────────────────────

export const listSubitems = (iterationId: string): Promise<RequirementSubitem[]> =>
  invoke(() => bridge().list_subitems(iterationId))

export const createSubitem = (
  iterationId: string,
  input: CreateSubitemInput,
): Promise<RequirementSubitem> => invoke(() => bridge().create_subitem(iterationId, input))

export const updateSubitem = (
  subitemId: string,
  patch: UpdateSubitemInput,
): Promise<RequirementSubitem> => invoke(() => bridge().update_subitem(subitemId, patch))

export const setSubitemStatus = (
  subitemId: string,
  status: RequirementStatus,
): Promise<RequirementSubitem> => invoke(() => bridge().set_subitem_status(subitemId, status))

export const deleteSubitem = (subitemId: string): Promise<boolean> =>
  invoke(() => bridge().delete_subitem(subitemId))

// ── Bug ──────────────────────────────────────────────────

export const listBugs = (projectId: string): Promise<BugItem[]> =>
  invoke(() => bridge().list_bugs(projectId))

export const createBug = (projectId: string, input: CreateBugInput): Promise<BugItem> =>
  invoke(() => bridge().create_bug(projectId, input))

export const updateBug = (bugId: string, patch: UpdateBugInput): Promise<BugItem> =>
  invoke(() => bridge().update_bug(bugId, patch))

export const deleteBug = (bugId: string): Promise<boolean> =>
  invoke(() => bridge().delete_bug(bugId))

export const setBugStatus = (bugId: string, status: BugStatus): Promise<BugItem> =>
  invoke(() => bridge().set_bug_status(bugId, status))

export const resolveBugLink = (linkedIterationId: string): Promise<BugLinkInfo | null> =>
  invoke(() => bridge().resolve_bug_link(linkedIterationId))

// ── 待办提醒 ──────────────────────────────────────────────

export const getTodoReminders = (): Promise<TodoReminder[]> =>
  invoke(() => bridge().get_todo_reminders())

// ── 导入 / 导出 ──────────────────────────────────────────────

/** 弹 .md 文件框 -> ParsedProject。取消返回 None。 */
export const parseMdImport = (): Promise<ParseMdResult | null> =>
  invoke(() => bridge().parse_md_import())

/** 应用完整导入（基础/智能共用统一写入路径）。
 *  target={project_id} 导入已有项目；target={name} 新建项目。reuse_id 由 parsed.reuse_id
 *  决定（基础导入 true / 智能导入 false），由前端按来源注入。 */
export const applyFullImport = (
  target: ImportTarget,
  parsed: ParsedProject,
): Promise<Project> => invoke(() => bridge().apply_full_import(target, parsed))

/** 智能导入第①步：校验配置 -> 弹文件框 -> 读文本 -> 校验长度。取消返回 null。 */
export const pickSmartImportFile = (): Promise<SmartPickResult | null> =>
  invoke(() => bridge().pick_smart_import_file())

/** 智能导入第②步：调 LLM 结构化 -> ParsedProject（预览用）。
 *  智能导入数据无原始 ID，提交时 reuse_id=false（全新建），由 ImportPreviewPanel 注入。 */
export const runSmartImport = (text: string, filename: string): Promise<SmartRunResult> =>
  invoke(() => bridge().run_smart_import(text, filename))

/** 导出项目为 .md 双轨格式（frontmatter 权威 + 正文渲染）。include_bug 决定是否含 bug 段。 */
export const exportProjectMd = (projectId: string, includeBug: boolean): Promise<string | null> =>
  invoke(() => bridge().export_project_md(projectId, includeBug))

// ── 导入前备份与回滚 ──────────────────────────────────────

/** 返回导入前备份清单（最新在前）。 */
export const listImportBackups = (): Promise<ImportBackupEntry[]> =>
  invoke(() => bridge().list_import_backups())

/** 回滚到指定导入前备份点（破坏性，覆盖当前库）。 */
export const restoreImportBackup = (backupId: string): Promise<boolean> =>
  invoke(() => bridge().restore_backup(backupId))

/** 删除单个导入前备份。 */
export const deleteImportBackup = (backupId: string): Promise<boolean> =>
  invoke(() => bridge().delete_backup(backupId))

// ── 存储位置 ──────────────────────────────────────────────

export const getStorageInfo = (): Promise<StorageInfo> =>
  invoke(() => bridge().get_storage_info())

export const pickStorageDir = (): Promise<string | null> =>
  invoke(() => bridge().pick_storage_dir())

export const migrateStorage = (newDir: string): Promise<StorageInfo> =>
  invoke(() => bridge().migrate_storage(newDir))

// ── 设置 ──────────────────────────────────────────────────

export const getSettings = (): Promise<AppSettings> => invoke(() => bridge().get_settings())

export const updateSettings = (patch: Partial<AppSettings>): Promise<AppSettings> =>
  invoke(() => bridge().update_settings(patch))

/** LLM 测试连接配置（表单草稿，未保存也能测试）。 */
export interface LlmTestConfig {
  base_url?: string
  api_key?: string
  model?: string
  timeout?: number
}

export interface LlmTestResult {
  ok: true
  model: string
  reply: string
}

/** 测试 LLM 连接（轻量 chat 请求）。config 为空时用已落盘设置。 */
export const testLlm = (config?: LlmTestConfig): Promise<LlmTestResult> =>
  invoke(() => bridge().test_llm(config ?? null))

// ── 系统 ─────────────────────────────────────────────────

/** 用系统默认浏览器打开外部链接（避免在 webview 内导航）。 */
export const openExternalUrl = (url: string): Promise<boolean> =>
  invoke(() => bridge().open_external_url(url))

/** 关于弹窗头像缓存（图片 B）。 */
export interface CachedAvatar {
  exists: true
  /** 形如 `data:image/jpeg;base64,...`，可直接用于 `<img src>`。 */
  data: string
}
export interface AvatarMissing {
  exists: false
}
export type AvatarInfo = CachedAvatar | AvatarMissing

/** 读取缓存的最新头像（用户访问过仓库后才有）。 */
export const getAvatar = (): Promise<AvatarInfo> => invoke(() => bridge().get_avatar())

/** 拉取作者 GitHub 最新头像写入 storage_dir/avatar.jpg（图片 B）。
 * 失败返回 ``{updated:false,reason:"..."}``，不抛错。 */
export const refreshAvatar = (): Promise<{ updated: boolean; reason?: string }> =>
  invoke(() => bridge().refresh_avatar())
