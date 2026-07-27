/** 状态标签映射（与 Python STATUS_LABEL 共享语义）。 */
export type RequirementStatus = 'todo' | 'ui_done_waiting_backend' | 'done' | 'deferred'

export const STATUS_LABEL: Record<RequirementStatus, string> = {
  todo: 'to do',
  ui_done_waiting_backend: 'UI完成等待后端',
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
  created_at: string
  updated_at: string
}
