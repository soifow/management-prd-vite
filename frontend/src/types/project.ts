import type { RequirementItem } from './requirement'

/** 项目详情 */
export interface Project {
  id: string
  name: string
  items: RequirementItem[]
  created_at: string
  updated_at: string
}

/** 项目汇总（侧边栏）。list_date 的口径由设置 project_list_date_mode 决定 */
export interface ProjectSummary {
  id: string
  name: string
  requirement_count: number
  list_date: string | null // ISO yyyy-MM-dd，口径随 project_list_date_mode 变化
  updated_at: string
}
