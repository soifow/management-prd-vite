import type { RequirementItem } from '@/types'

/** 日期分组内的模块段（同模块的需求聚在一起）。 */
export interface DateSegment {
  module: string
  items: RequirementItem[]
}

/** 按日期聚合的分组。 */
export interface DateGroup {
  date: string // yyyy-MM-dd
  items: RequirementItem[] // 已按 module, feature 排好序
  segments: DateSegment[] // 同模块聚成一段
}

const UNGROUPED = '（未分组）'

/**
 * 按「日期」聚合需求（类似更新日志）：日期倒序（新->旧），
 * 同一日期内同模块相邻排在一起（按 module 再 feature 排序）。
 */
export function groupByDate(items: RequirementItem[]): DateGroup[] {
  // 先排序：module -> feature -> date（同模块相邻；同模块内按 feature 聚拢）
  const sorted = [...items].sort((a, b) => {
    if (a.module !== b.module) return a.module.localeCompare(b.module)
    if (a.feature !== b.feature) return a.feature.localeCompare(b.feature)
    return a.date.localeCompare(b.date)
  })

  // 按 date 分组；遍历时按排序后的顺序，但分组结果需 date 倒序
  const map = new Map<string, RequirementItem[]>()
  for (const it of sorted) {
    if (!map.has(it.date)) map.set(it.date, [])
    map.get(it.date)!.push(it)
  }

  const groups: DateGroup[] = []
  for (const [date, dayItems] of map.entries()) {
    // dayItems 已按 module, feature 排好；切分模块段
    const segments: DateSegment[] = []
    for (const it of dayItems) {
      const label = it.module || UNGROUPED
      const last = segments[segments.length - 1]
      if (last && last.module === label) {
        last.items.push(it)
      } else {
        segments.push({ module: label, items: [it] })
      }
    }
    groups.push({ date, items: dayItems, segments })
  }

  // 日期倒序（新 -> 旧）
  groups.sort((a, b) => b.date.localeCompare(a.date))
  return groups
}
