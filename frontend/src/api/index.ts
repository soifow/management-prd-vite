/**
 * 后端 WebApi 的 TypeScript 封装层。
 */

import { isApiErrorEnvelope } from '@/types/api'
import type { StorageInfo } from '@/types/api'
import type { ParsedRequirement, PickParseResult } from '@/types/import'
import type { Project, ProjectSummary } from '@/types/project'
import type { RequirementItem, RequirementStatus } from '@/types/requirement'
import type { AppSettings } from '@/types/settings'
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

export const listModules = (projectId: string): Promise<string[]> =>
  invoke(() => bridge().list_modules(projectId))

export const listFeatures = (projectId: string, module: string): Promise<string[]> =>
  invoke(() => bridge().list_features(projectId, module))

export const listIterations = (
  projectId: string,
  module: string,
  feature: string,
): Promise<RequirementItem[]> =>
  invoke(() => bridge().list_iterations(projectId, module, feature))

// ── 需求 ────────────────────────────────────────────────────

export interface CreateRequirementInput {
  module: string
  feature: string
  content: string
  status: RequirementStatus
  date: string
  completion_deadline: string | null
}

export interface UpdateRequirementInput {
  module?: string
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

// ── 待办提醒 ──────────────────────────────────────────────

export const getTodoReminders = (): Promise<TodoReminder[]> =>
  invoke(() => bridge().get_todo_reminders())

// ── 导入 / 导出 ──────────────────────────────────────────────

export const pickAndParseImport = (): Promise<PickParseResult | null> =>
  invoke(() => bridge().pick_and_parse_import())

export const applyImport = (
  projectId: string,
  requirements: ParsedRequirement[],
): Promise<Project> => invoke(() => bridge().apply_import(projectId, requirements))

export const applyImportAsNewProject = (
  name: string,
  requirements: ParsedRequirement[],
): Promise<Project> =>
  invoke(() => bridge().apply_import_as_new_project(name, requirements))

export const exportProject = (projectId: string): Promise<string | null> =>
  invoke(() => bridge().export_project(projectId))

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
