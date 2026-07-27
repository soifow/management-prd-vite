import type { RequirementItem } from './requirement'

/** 项目详情 */
export interface Project {
  id: string
  name: string
  items: RequirementItem[]
  created_at: string
  updated_at: string
}

/** 项目汇总（侧边栏） */
export interface ProjectSummary {
  id: string
  name: string
  requirement_count: number
  latest_done_or_ui_date: string | null // ISO yyyy-MM-dd
  updated_at: string
}
