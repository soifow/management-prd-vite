/** Bug 管理相关类型定义（与后端 models/bug.py 共享语义）。 */

export type BugLevel = 'P0' | 'P1' | 'P2' | 'P3' | 'P4'
export type BugStatus = 'open' | 'fixed'

export const LEVEL_LABEL: Record<BugLevel, string> = {
  P0: 'P0 核心缺陷',
  P1: 'P1 Critical',
  P2: 'P2 High',
  P3: 'P3 Medium',
  P4: 'P4 Low',
}

export const LEVEL_TAG_TYPE: Record<BugLevel, string> = {
  P0: 'danger',
  P1: 'danger',
  P2: 'warning',
  P3: 'info',
  P4: 'success',
}

export const BUG_STATUS_LABEL: Record<BugStatus, string> = {
  open: '待修复',
  fixed: '已修复',
}

export const BUG_STATUS_TAG_TYPE: Record<BugStatus, string> = {
  open: 'danger',
  fixed: 'success',
}

/** 一条 bug 记录。 */
export interface BugItem {
  id: string
  project_id: string
  module: string
  content: string
  level: BugLevel
  status: BugStatus
  linked_iteration_id: string | null
  date: string // ISO yyyy-MM-dd
  created_at: string
  updated_at: string
}

/** 新建 bug 入参。 */
export interface CreateBugInput {
  module: string
  content: string
  level: BugLevel
  status: BugStatus
  linked_iteration_id: string | null
  date: string
}

/** 更新 bug 入参（部分字段）。 */
export interface UpdateBugInput {
  module?: string
  content?: string
  level?: BugLevel
  status?: BugStatus
  linked_iteration_id?: string
  /** true 则置 NULL（优先级高于 linked_iteration_id） */
  clear_linked?: boolean
  date?: string
}

/** resolve_bug_link 返回（用于详情页关联卡片 + 跨视图跳转四步）。 */
export interface BugLinkInfo {
  item_id: string
  project_id: string
  module: string
  feature: string
  content: string
  date: string
}
