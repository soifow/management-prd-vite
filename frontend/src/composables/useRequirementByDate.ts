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
 *
 * 排序规则：
 * - 段内（同一日期同一模块）：未完成在前、已完成（done）靠后，同组维持 feature->date 顺序；
 * - 段间（同一日期不同模块）：段内所有 item 均 done 则该模块整体算已完成、靠后；
 *   只要有一条未完成，该模块靠前。同组（同为已完成/同为未完成）按模块名排序。
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
    // 按模块分桶（同模块聚成一段；dayItems 已按 module 排好，桶内保留 feature->date 顺序）
    const segMap = new Map<string, RequirementItem[]>()
    for (const it of dayItems) {
      const label = it.module || UNGROUPED
      if (!segMap.has(label)) segMap.set(label, [])
      segMap.get(label)!.push(it)
    }
    // 段内：未完成在前、已完成靠后（稳定）；段间：全完成段靠后，同组按模块名
    const segments: DateSegment[] = Array.from(segMap.entries())
      .map(([module, items]) => ({
        module,
        items: [...items].sort(
          (a, b) => (a.status === 'done' ? 1 : 0) - (b.status === 'done' ? 1 : 0),
        ),
      }))
      .sort((a, b) => {
        const aDone = a.items.every((i) => i.status === 'done') ? 1 : 0
        const bDone = b.items.every((i) => i.status === 'done') ? 1 : 0
        if (aDone !== bDone) return aDone - bDone
        return a.module.localeCompare(b.module)
      })
    groups.push({ date, items: dayItems, segments })
  }

  // 日期倒序（新 -> 旧）
  groups.sort((a, b) => b.date.localeCompare(a.date))
  return groups
}
