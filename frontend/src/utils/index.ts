import type { BugItem, BugLevel, BugStatus } from '@/types'

const LEVEL_ORDER: Record<BugLevel, number> = { P0: 0, P1: 1, P2: 2, P3: 3, P4: 4 }
const BUG_STATUS_ORDER: Record<BugStatus, number> = { open: 0, fixed: 1 }

/**
 * Bug 列表统一排序：状态（open 在前 / fixed 靠后）→ 严重等级（P0 最前）→ 提交早晚（created_at 升序）。
 * 注：bugs 表无项目内自增编号，第 3 级用 created_at 升序作「提交早的在前」代理。
 */
export function sortBugs(list: BugItem[]): BugItem[] {
  return [...list].sort((a, b) => {
    if (a.status !== b.status) return BUG_STATUS_ORDER[a.status] - BUG_STATUS_ORDER[b.status]
    if (a.level !== b.level) return LEVEL_ORDER[a.level] - LEVEL_ORDER[b.level]
    return a.created_at.localeCompare(b.created_at)
  })
}

/** 把 date (yyyy-MM-dd 或 yyyy/MM/dd) 统一格式化为 yyyy-MM-dd 显示。 */
export function formatDate(date: string): string {
  if (!date) return ''
  const normalized = date.replace(/\//g, '-')
  return normalized.split('-').length === 3 ? normalized : date
}

/** 把 date 转为 yyyy-MM-dd（如果没有则返回空）。 */
export function isoDate(d?: Date | string): string {
  if (!d) return ''
  if (typeof d === 'string') return d.slice(0, 10)
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}
