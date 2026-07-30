/**
 * 待办提醒类型（与 Python WebApi.get_todo_reminders 返回结构契约一致）。
 *
 * 后端单点完成阈值过滤、剩余天数计算与排序，返回扁平有序列表；
 * 前端按 bucket/remaining_days 分组渲染。
 */

import type { RequirementStatus } from './requirement'

/** 待办分组桶：决定在抽屉中的分组位置与排序。 */
export type TodoBucket = 'overdue' | 'remaining' | 'no_deadline' | 'deferred'

/** 一条待办提醒（跨项目聚合）。 */
export interface TodoReminder {
  /** 需求迭代 id（点击跳转时用于选中该迭代） */
  item_id: string
  project_id: string
  project_name: string
  module: string
  feature: string
  /** 需求简述（内容正文，前端截断展示） */
  content: string
  status: RequirementStatus
  /** 迭代日期 ISO yyyy-MM-dd */
  date: string
  /** 完成时限 ISO yyyy-MM-dd 或 null（无时限） */
  completion_deadline: string | null
  /** 剩余天数（deadline - today）；overdue 为负，no_deadline/deferred 为 null */
  remaining_days: number | null
  bucket: TodoBucket
}
