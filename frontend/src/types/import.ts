import type { BugLevel, BugStatus } from './bug'
import type { RequirementStatus } from './requirement'

/**
 * 导入预览数据模型（.md 双轨格式 frontmatter 权威源）。
 *
 * 与后端 `management_prd.models.data.ParsedProject` 契约一致：所有引用字段
 * （`iterations.modules` / `bugs.modules` / `bugs.linked`）使用 frontmatter 内的
 * 原始 DB id，导入时由后端 `apply_full_import` 维护 id_map 重写。
 *
 * `selected` 字段为导入预览可编辑的勾选标记（后端默认 True，前端可取消以排除该项）。
 * `reuse_id` 非持久化字段，提交时由前端按导入来源（基础=true / 智能=false）注入，
 * 后端据此决定 ID 复用/映射还是全新建。
 */

/** frontmatter 模块项。 */
export interface ParsedModule {
  id: string
  name: string
}

/** frontmatter 子需求项（挂某迭代下，随迭代整体导入）。 */
export interface ParsedSubitem {
  seq: number
  content: string
  status: RequirementStatus
  /** ISO yyyy-MM-dd 或 null（deferred 强制 null） */
  completion_deadline: string | null
  selected: boolean
}

/** frontmatter 迭代项。modules 为原始 module id 列表。 */
export interface ParsedIteration {
  id: string
  feature: string
  modules: string[]
  content: string
  status: RequirementStatus
  date: string // ISO yyyy-MM-dd
  /** ISO yyyy-MM-dd 或 null（deferred 强制 null） */
  completion_deadline: string | null
  created_at: string
  updated_at: string
  subitems: ParsedSubitem[]
  selected: boolean
}

/** frontmatter bug 项。linked 引用某 iteration.id（原始 id），未命中置 null。 */
export interface ParsedBug {
  id: string
  content: string
  level: BugLevel
  status: BugStatus
  modules: string[]
  /** 引用某 iteration.id；null=无关联 */
  linked: string | null
  date: string // ISO yyyy-MM-dd
  created_at: string
  updated_at: string
  selected: boolean
}

/** 从 .md frontmatter 解析出的项目快照（导入预览根对象）。 */
export interface ParsedProject {
  project_id: string
  name: string
  created_at: string
  updated_at: string
  modules: ParsedModule[]
  iterations: ParsedIteration[]
  bugs: ParsedBug[]
  includes_bug: boolean
  /**
   * 导入来源标记：true=基础导入（ID 复用/冲突映射），false=智能导入（全新建）。
   * 非持久化字段，提交时由前端注入；后端 `apply_full_import` 据此决定 reuse_id。
   */
  reuse_id?: boolean
}

/** apply_full_import 的目标：新建项目（name）或已有项目（project_id）。二者互斥。 */
export interface ImportTarget {
  project_id?: string
  name?: string
}

/** parse_md_import 返回结果：解析出的项目快照 + 文件名（去扩展名，用于推测项目名）。 */
export interface ParseMdResult {
  parsed: ParsedProject
  filename: string
}
