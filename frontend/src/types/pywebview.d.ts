/**
 * PyWebView 桥接全局类型声明。
 */

import type { ApiErrorEnvelope } from './api'
import type { BugItem, BugLinkInfo, BugStatus, CreateBugInput, UpdateBugInput } from './bug'
import type { ImportTarget, ParseMdResult, ParsedProject } from './import'
import type { Module } from './module'
import type { Project, ProjectSummary } from './project'
import type { RequirementItem, RequirementStatus } from './requirement'
import type { AppSettings } from './settings'
import type { CreateSubitemInput, RequirementSubitem, UpdateSubitemInput } from './subitem'
import type { TodoReminder } from './todo'

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
  list_modules(project_id: string): Promise<Module[] | ApiErrorEnvelope>
  create_module(project_id: string, name: string): Promise<Module | ApiErrorEnvelope>
  delete_module(module_id: string): Promise<boolean | ApiErrorEnvelope>
  list_features(project_id: string): Promise<string[] | ApiErrorEnvelope>
  list_iterations(
    project_id: string,
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

  // ── 迭代级子需求 ──
  list_subitems(iteration_id: string): Promise<RequirementSubitem[] | ApiErrorEnvelope>
  create_subitem(
    iteration_id: string,
    input: CreateSubitemInput,
  ): Promise<RequirementSubitem | ApiErrorEnvelope>
  update_subitem(
    subitem_id: string,
    patch: UpdateSubitemInput,
  ): Promise<RequirementSubitem | ApiErrorEnvelope>
  set_subitem_status(
    subitem_id: string,
    status: RequirementStatus,
  ): Promise<RequirementSubitem | ApiErrorEnvelope>
  delete_subitem(subitem_id: string): Promise<boolean | ApiErrorEnvelope>

  // ── Bug ──
  list_bugs(project_id: string): Promise<BugItem[] | ApiErrorEnvelope>
  create_bug(project_id: string, input: CreateBugInput): Promise<BugItem | ApiErrorEnvelope>
  update_bug(bug_id: string, patch: UpdateBugInput): Promise<BugItem | ApiErrorEnvelope>
  delete_bug(bug_id: string): Promise<boolean | ApiErrorEnvelope>
  set_bug_status(bug_id: string, status: BugStatus): Promise<BugItem | ApiErrorEnvelope>
  resolve_bug_link(linked_iteration_id: string): Promise<BugLinkInfo | null | ApiErrorEnvelope>

  // ── 导入 / 导出 ──
  /** 弹 .md 文件框 -> ParsedProject。取消返回 None。 */
  parse_md_import(): Promise<ParseMdResult | null | ApiErrorEnvelope>
  /** 应用完整导入（基础/智能共用统一写入路径）。 */
  apply_full_import(
    target: ImportTarget,
    parsed: ParsedProject,
  ): Promise<Project | ApiErrorEnvelope>
  /** 导出项目为 .md 双轨格式（frontmatter + 正文）。 */
  export_project_md(
    project_id: string,
    include_bug: boolean,
  ): Promise<string | null | ApiErrorEnvelope>

  // ── 存储位置 ──
  get_storage_info(): Promise<StorageInfo | ApiErrorEnvelope>
  pick_storage_dir(): Promise<string | null | ApiErrorEnvelope>
  migrate_storage(new_dir: string): Promise<StorageInfo | ApiErrorEnvelope>

  // ── 设置 ──
  get_settings(): Promise<AppSettings | ApiErrorEnvelope>
  update_settings(patch: Partial<AppSettings>): Promise<AppSettings | ApiErrorEnvelope>
  /** 测试 LLM 连接（轻量 chat 请求）。config 为空时用已落盘设置。 */
  test_llm(config: {
    base_url?: string
    api_key?: string
    model?: string
    timeout?: number
  } | null): Promise<
    | { ok: true; model: string; reply: string }
    | ApiErrorEnvelope
  >
  /** 智能导入：弹文件框 -> 读文本 -> LLM 结构化 -> ParsedProject（预览用）。取消返回 None。 */
  smart_import(): Promise<ParseMdResult | null | ApiErrorEnvelope>

  // ── 系统 ──
  open_external_url(url: string): Promise<boolean | ApiErrorEnvelope>
  get_avatar(): Promise<
    | { exists: true; data: string }
    | { exists: false }
    | ApiErrorEnvelope
  >
  refresh_avatar(): Promise<
    | { updated: true }
    | { updated: false; reason: string }
    | ApiErrorEnvelope
  >
}

declare global {
  interface Window {
    /** PyWebView 注入的桥接对象；在 pywebviewready 事件后可用。 */
    pywebview?: {
      api: PyWebViewApi
    }
  }
}
