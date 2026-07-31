import type { RequirementItem, RequirementStatus } from '@/types'

export interface RequirementFilters {
  dateFrom: string
  dateTo: string
  statuses: RequirementStatus[]
  keyword: string
}

/**
 * 组合筛选（作用于迭代记录）：日期区间 ∩ 状态多选 ∩ 关键字模糊。AND 关系。
 * v3：单 date（直接比对 item.date）。
 */
export function useRequirementFilter(
  items: RequirementItem[],
  filters: RequirementFilters,
): RequirementItem[] {
  return items.filter((item) => {
    if (filters.dateFrom && item.date < filters.dateFrom) return false
    if (filters.dateTo && item.date > filters.dateTo) return false
    if (filters.statuses.length > 0 && !filters.statuses.includes(item.status)) return false
    if (filters.keyword) {
      const kw = filters.keyword.toLowerCase()
      if (
        !item.content.toLowerCase().includes(kw) &&
        !item.feature.toLowerCase().includes(kw) &&
        !item.modules.some((m) => m.toLowerCase().includes(kw))
      ) {
        return false
      }
    }
    return true
  })
}
