import { describe, it, expect } from 'vitest'

import { buildFeatureTree, groupByModule } from '../useRequirementTree'
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

const items = [
  makeItem('模块A', '功能X', 'v1', 'done', '2026-03-27'),
  makeItem('模块A', '功能X', 'v2', 'todo', '2026-05-20'),
  makeItem('模块A', '功能Y', '需求Y', 'done', '2026-06-29'),
  makeItem('模块B', '功能Z', '需求Z', 'ui_done_waiting_backend', '2026-07-15'),
]

const noFilters = { dateFrom: '', dateTo: '', statuses: [], keyword: '' }

describe('buildFeatureTree', () => {
  it('按 (module, feature) 聚合，功能X 两条迭代合一', () => {
    const nodes = buildFeatureTree(items, noFilters)
    expect(nodes).toHaveLength(3)
    const x = nodes.find((n) => n.feature === '功能X')!
    expect(x.iterations).toHaveLength(2)
    expect(x.count).toBe(2)
    // 按日期升序，最新为 v2（2026-05-20）
    expect(x.latestDate).toBe('2026-05-20')
    expect(x.latestStatus).toBe('todo')
  })

  it('过滤会裁掉迭代；功能无剩余则不出现', () => {
    const nodes = buildFeatureTree(items, {
      dateFrom: '2026-06-01',
      dateTo: '',
      statuses: [],
      keyword: '',
    })
    // 仅 2026-06-29 和 2026-07-15 命中
    const feats = nodes.map((n) => n.feature).sort()
    expect(feats).toEqual(['功能Y', '功能Z'])
  })

  it('按 module 再 feature 排序', () => {
    const nodes = buildFeatureTree(items, noFilters)
    expect(nodes.map((n) => `${n.module}/${n.feature}`)).toEqual([
      '模块A/功能X',
      '模块A/功能Y',
      '模块B/功能Z',
    ])
  })
})

describe('groupByModule', () => {
  it('按模块分组', () => {
    const nodes = buildFeatureTree(items, noFilters)
    const grouped = groupByModule(nodes)
    expect(grouped.map((g) => g.module)).toEqual(['模块A', '模块B'])
    const a = grouped.find((g) => g.module === '模块A')!
    expect(a.features).toHaveLength(2)
  })
})
