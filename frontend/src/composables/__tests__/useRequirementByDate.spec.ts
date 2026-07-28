import { describe, it, expect } from 'vitest'

import { groupByDate } from '../useRequirementByDate'
import type { RequirementItem } from '@/types'

function makeItem(
  module: string,
  feature: string,
  content: string,
  status: RequirementItem['status'],
  d: string,
): RequirementItem {
  return {
    id: `${module}-${feature}-${d}`,
    project_id: 'p1',
    module,
    feature,
    content,
    status,
    date: d,
    created_at: d,
    updated_at: d,
  }
}

describe('groupByDate', () => {
  it('按日期降序分组', () => {
    const items = [
      makeItem('模块A', '功能X', 'v1', 'done', '2026-03-27'),
      makeItem('模块A', '功能X', 'v2', 'todo', '2026-05-20'),
      makeItem('模块B', '功能Z', '需求Z', 'done', '2026-06-29'),
    ]
    const groups = groupByDate(items)
    expect(groups.map((g) => g.date)).toEqual(['2026-06-29', '2026-05-20', '2026-03-27'])
  })

  it('同日期内同模块相邻排在一起（segments 切分）', () => {
    const items = [
      makeItem('模块B', '功能Z', 'B1', 'done', '2026-06-29'),
      makeItem('模块A', '功能X', 'A1', 'done', '2026-06-29'),
      makeItem('模块A', '功能Y', 'A2', 'todo', '2026-06-29'),
    ]
    const groups = groupByDate(items)
    expect(groups).toHaveLength(1)
    expect(groups[0].date).toBe('2026-06-29')
    // segments 按模块升序：模块A 段在前（含两条），模块B 段在后（一条）
    expect(groups[0].segments.map((s) => s.module)).toEqual(['模块A', '模块B'])
    expect(groups[0].segments[0].items).toHaveLength(2)
    expect(groups[0].segments[1].items).toHaveLength(1)
  })

  it('空模块归为「（未分组）」', () => {
    const items = [makeItem('', '无名', '需求X', 'todo', '2026-07-15')]
    const groups = groupByDate(items)
    expect(groups[0].segments[0].module).toBe('（未分组）')
  })

  it('空数组返回空', () => {
    expect(groupByDate([])).toEqual([])
  })

  it('同日期多条迭代：group.items 数量正确', () => {
    const items = [
      makeItem('模块A', '功能X', 'v1', 'done', '2026-06-29'),
      makeItem('模块A', '功能X', 'v2', 'todo', '2026-06-29'),
      makeItem('模块A', '功能X', 'v3', 'done', '2026-06-29'),
    ]
    const groups = groupByDate(items)
    expect(groups).toHaveLength(1)
    expect(groups[0].items).toHaveLength(3)
  })
})
