/** 迭代级子需求（与后端 RequirementSubitem 契约一致）。 */

import type { RequirementStatus } from './requirement'

/** 迭代级子需求（某次迭代下的若干细小点，各自独立状态）。 */
export interface RequirementSubitem {
  id: string
  iteration_id: string
  seq: number
  content: string
  status: RequirementStatus
  completion_deadline: string | null
  created_at: string
  updated_at: string
}

export interface CreateSubitemInput {
  iteration_id: string
  content: string
  status?: RequirementStatus
  completion_deadline?: string | null
}

export interface UpdateSubitemInput {
  content?: string
  status?: RequirementStatus
  completion_deadline?: string
  /** true 则置 NULL（优先级高于 completion_deadline） */
  clear_completion_deadline?: boolean
}
