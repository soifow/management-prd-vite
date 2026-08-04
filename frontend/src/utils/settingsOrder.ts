/**
 * 设置页分组顺序工具。
 *
 * 顺序数组始终应包含「全部已注册分组 key」：已持久化的 key 保持原顺序在前，
 * 缺失/未知的 key 按注册顺序补齐到末尾。拖拽重排基于 key 数组操作。
 *
 * 新增分组只需在 SettingsPage 的 GROUPS 注册：normalizeOrder 会自动把它纳入
 * 顺序与重排，无需改动此处逻辑。
 */

/** 规范化分组 key 顺序：保留 base 中合法且去重的 key 顺序，补齐缺失的 allKeys。 */
export function normalizeOrder(base: string[], allKeys: readonly string[]): string[] {
  const valid = new Set(allKeys)
  const seen = new Set<string>()
  const ordered: string[] = []
  for (const k of base) {
    if (valid.has(k) && !seen.has(k)) {
      ordered.push(k)
      seen.add(k)
    }
  }
  for (const k of allKeys) {
    if (!seen.has(k)) {
      ordered.push(k)
      seen.add(k)
    }
  }
  return ordered
}

/**
 * 把 fromKey 移动到 toKey 所在位置（移除 fromKey 后，插入到 toKey 原索引处）。
 * 语义与旧实现一致：向下拖（from<to）摆在目标之后，向上拖（from>to）摆在目标之前。
 * key 不存在或两者相同则原样返回。
 */
export function moveKey(order: string[], fromKey: string, toKey: string): string[] {
  const from = order.indexOf(fromKey)
  const to = order.indexOf(toKey)
  if (from === -1 || to === -1 || from === to) return [...order]
  const next = [...order]
  next.splice(from, 1)
  next.splice(to, 0, fromKey)
  return next
}