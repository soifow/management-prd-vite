import type { RequirementItem } from '@/types'
import { STATUS_LABEL, STATUS_TAG_TYPE } from '@/types/requirement'
import type { RequirementStatus } from '@/types'

/** 功能聚合节点（模块 → 功能）。v4：多模块需求会在每个关联模块下各出现一份。 */
export interface FeatureNode {
  module: string
  feature: string
  iterations: RequirementItem[]
  latestDate: string
  latestStatus: RequirementStatus
  count: number
  /** 子需求进度摘要（开 `show_subitem_progress_in_tree` 时由后端/外部回填）。 */
  subitemProgress: { done: number; total: number } | null
}

/** 按「模块 → 功能」聚合需求（功能为叶子；同 (module, feature) 的多条为迭代）。

v4 改动：一条多 module 需求在其关联的每个模块下展开为一个 FeatureNode（同一份
iterations）。空关联（modules 为空）归入「（未分组）」。子需求进度摘要来自外部
传入的 ``progressMap``（feature -> {done,total}），由 store 在项目加载时批量查询。 */
export function buildFeatureTree(
  items: RequirementItem[],
  filters: {
    dateFrom: string
    dateTo: string
    statuses: RequirementStatus[]
    keyword: string
  },
  progressMap: Record<string, { done: number; total: number }> = {},
): FeatureNode[] {
  // 先过滤迭代记录
  const filtered = items.filter((item) => {
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

  // 展开多模块：一条记录在多个模块下各生成一个节点
  const expanded: { module: string; item: RequirementItem }[] = []
  for (const it of filtered) {
    const mods = it.modules.length > 0 ? it.modules : ['']
    for (const m of mods) {
      expanded.push({ module: m, item: it })
    }
  }

  // 聚合 (module, feature)
  const map = new Map<string, RequirementItem[]>()
  for (const e of expanded) {
    const key = `${e.module}\x00${e.item.feature}`
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(e.item)
  }

  const nodes: FeatureNode[] = []
  for (const [key, iters] of map.entries()) {
    const [module, feature] = key.split('\x00')
    const sorted = [...iters].sort((a, b) => a.date.localeCompare(b.date))
    const latest = sorted[sorted.length - 1]
    nodes.push({
      module,
      feature,
      iterations: sorted,
      latestDate: latest.date,
      latestStatus: latest.status,
      count: sorted.length,
      subitemProgress: progressMap[feature] ?? null,
    })
  }
  // 按 module 再 feature 排序
  nodes.sort((a, b) =>
    a.module === b.module ? a.feature.localeCompare(b.feature) : a.module.localeCompare(b.module),
  )
  return nodes
}

/** 把 feature 树按模块分组（树形渲染用）。

模块内排序：已完成（latestStatus==='done'）的 feature 靠后，其余在前；
同组内按 feature 名排序。模块间排序不变（按模块名）。 */
export function groupByModule(nodes: FeatureNode[]): { module: string; features: FeatureNode[] }[] {
  const map = new Map<string, FeatureNode[]>()
  for (const n of nodes) {
    const key = n.module || '（未分组）'
    if (!map.has(key)) map.set(key, [])
    map.get(key)!.push(n)
  }
  return Array.from(map.entries())
    .map(([module, features]) => ({
      module,
      features: [...features].sort((a, b) => {
        const ad = a.latestStatus === 'done' ? 1 : 0
        const bd = b.latestStatus === 'done' ? 1 : 0
        if (ad !== bd) return ad - bd // 已完成靠后
        return a.feature.localeCompare(b.feature) // 同组按 feature 名
      }),
    }))
    .sort((a, b) => a.module.localeCompare(b.module, 'zh-Hans-CN'))
}

export const STATUS_LABEL_MAP = STATUS_LABEL
export const STATUS_TAG_TYPE_MAP = STATUS_TAG_TYPE
