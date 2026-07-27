/** 把 date (yyyy-MM-dd 或 yyyy/MM/dd) 转为 YYMMDD 显示。 */
export function formatYymmdd(date: string): string {
  if (!date) return ''
  // 支持 yyyy-MM-dd 或 yyyy/MM/dd
  const normalized = date.replace(/\//g, '-')
  const parts = normalized.split('-')
  if (parts.length !== 3) return date
  return parts[0].slice(2) + parts[1] + parts[2]
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
