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
