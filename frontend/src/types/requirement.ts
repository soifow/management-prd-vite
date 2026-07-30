/** 状态标签映射（与 Python STATUS_LABEL 共享语义）。
 *
 * 注：原 'bug' 状态已移除 —— bug 改由独立的 bugs 表管理（见 ./bug.ts）。
 * 历史 status='bug' 的需求行在后端 schema v3 迁移中一次性搬入 bugs 表并删除。
 */
export type RequirementStatus = 'todo' | 'ui_done_waiting_backend' | 'done' | 'deferred'

export const STATUS_LABEL: Record<RequirementStatus, string> = {
  todo: 'to do',
  ui_done_waiting_backend: '等待对接',
  done: '完成',
  deferred: '暂缓',
}

export const STATUS_TAG_TYPE: Record<RequirementStatus, string> = {
  todo: 'info',
  ui_done_waiting_backend: 'warning',
  done: 'success',
  deferred: 'danger',
}

/** 需求迭代记录（单 date + feature）。 */
export interface RequirementItem {
  id: string
  project_id: string
  module: string
  feature: string
  content: string
  status: RequirementStatus
  date: string // ISO yyyy-MM-dd
  completion_deadline: string | null // ISO yyyy-MM-dd or null
  created_at: string
  updated_at: string
}
