/**
 * PyWebView 桥接全局类型声明。
 */

import type { ApiErrorEnvelope } from './api'
import type { BugItem, BugLinkInfo, BugStatus, CreateBugInput, UpdateBugInput } from './bug'
import type { ParsedRequirement, PickParseResult } from './import'
import type { Project, ProjectSummary } from './project'
import type { RequirementItem, RequirementStatus } from './requirement'
import type { AppSettings } from './settings'
import type { TodoReminder } from './todo'

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
  completion_deadline?: string
  clear_completion_deadline?: boolean
}

/** 后端 WebApi 暴露给前端的原始方法集合（方法名与后端 snake_case 一致）。 */
export interface PyWebViewApi {
  // ── 项目 ──
  list_projects(): Promise<ProjectSummary[] | ApiErrorEnvelope>
  get_project(project_id: string): Promise<Project | ApiErrorEnvelope>
  create_project(name: string): Promise<ProjectSummary | ApiErrorEnvelope>
  rename_project(project_id: string, name: string): Promise<ProjectSummary | ApiErrorEnvelope>
  delete_project(project_id: string): Promise<boolean | ApiErrorEnvelope>
  list_modules(project_id: string): Promise<string[] | ApiErrorEnvelope>
  list_features(project_id: string, module: string): Promise<string[] | ApiErrorEnvelope>
  list_iterations(
    project_id: string,
    module: string,
    feature: string,
  ): Promise<RequirementItem[] | ApiErrorEnvelope>

  // ── 需求 ──
  create_requirement(
    project_id: string,
    input: CreateRequirementInput,
  ): Promise<RequirementItem | ApiErrorEnvelope>
  update_requirement(
    item_id: string,
    patch: UpdateRequirementInput,
  ): Promise<RequirementItem | ApiErrorEnvelope>
  set_requirement_status(
    item_id: string,
    status: RequirementStatus,
  ): Promise<RequirementItem | ApiErrorEnvelope>
  delete_requirement(item_id: string): Promise<boolean | ApiErrorEnvelope>
  get_todo_reminders(): Promise<TodoReminder[] | ApiErrorEnvelope>

  // ── Bug ──
  list_bugs(project_id: string): Promise<BugItem[] | ApiErrorEnvelope>
  create_bug(project_id: string, input: CreateBugInput): Promise<BugItem | ApiErrorEnvelope>
  update_bug(bug_id: string, patch: UpdateBugInput): Promise<BugItem | ApiErrorEnvelope>
  delete_bug(bug_id: string): Promise<boolean | ApiErrorEnvelope>
  set_bug_status(bug_id: string, status: BugStatus): Promise<BugItem | ApiErrorEnvelope>
  resolve_bug_link(linked_iteration_id: string): Promise<BugLinkInfo | null | ApiErrorEnvelope>

  // ── 导入 / 导出 ──
  pick_and_parse_import(): Promise<PickParseResult | null | ApiErrorEnvelope>
  apply_import(
    project_id: string,
    requirements: ParsedRequirement[],
  ): Promise<Project | ApiErrorEnvelope>
  apply_import_as_new_project(
    name: string,
    requirements: ParsedRequirement[],
  ): Promise<Project | ApiErrorEnvelope>
  export_project(project_id: string): Promise<string | null | ApiErrorEnvelope>

  // ── 存储位置 ──
  get_storage_info(): Promise<StorageInfo | ApiErrorEnvelope>
  pick_storage_dir(): Promise<string | null | ApiErrorEnvelope>
  migrate_storage(new_dir: string): Promise<StorageInfo | ApiErrorEnvelope>

  // ── 设置 ──
  get_settings(): Promise<AppSettings | ApiErrorEnvelope>
  update_settings(patch: Partial<AppSettings>): Promise<AppSettings | ApiErrorEnvelope>
}

declare global {
  interface Window {
    /** PyWebView 注入的桥接对象；在 pywebviewready 事件后可用。 */
    pywebview?: {
      api: PyWebViewApi
    }
  }
}
