import { describe, it, expect } from 'vitest'

import { useRequirementFilter } from '../useRequirementFilter'
import type { RequirementItem } from '@/types'

function makeItem(
  content: string,
  status: RequirementItem['status'],
  module: string,
  feature: string,
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
  makeItem('需求A内容', 'done', '模块1', '功能A', '2026-06-29'),
  makeItem('需求B内容', 'todo', '模块1', '功能B', '2026-08-01'),
  makeItem('需求C内容', 'ui_done_waiting_backend', '模块2', '功能C', '2026-07-15'),
  makeItem('需求D内容', 'deferred', '模块2', '功能D', '2026-05-20'),
]

describe('useRequirementFilter', () => {
  it('无过滤条件返回全部', () => {
    expect(
      useRequirementFilter(items, { dateFrom: '', dateTo: '', statuses: [], keyword: '' }),
    ).toHaveLength(4)
  })

  it('按状态多选过滤', () => {
    const result = useRequirementFilter(items, {
      dateFrom: '',
      dateTo: '',
      statuses: ['done', 'todo'],
      keyword: '',
    })
    expect(result).toHaveLength(2)
  })

  it('按日期区间过滤', () => {
    const result = useRequirementFilter(items, {
      dateFrom: '2026-05-01',
      dateTo: '2026-05-31',
      statuses: [],
      keyword: '',
    })
    expect(result).toHaveLength(1)
    expect(result[0].feature).toBe('功能D')
  })

  it('关键字模糊匹配（内容/功能/模块，不区分大小写）', () => {
    const byContent = useRequirementFilter(items, {
      dateFrom: '',
      dateTo: '',
      statuses: [],
      keyword: '需求a',
    })
    expect(byContent).toHaveLength(1)
    expect(byContent[0].feature).toBe('功能A')

    const byModule = useRequirementFilter(items, {
      dateFrom: '',
      dateTo: '',
      statuses: [],
      keyword: '模块2',
    })
    expect(byModule).toHaveLength(2)

    const byFeature = useRequirementFilter(items, {
      dateFrom: '',
      dateTo: '',
      statuses: [],
      keyword: '功能B',
    })
    expect(byFeature).toHaveLength(1)
  })

  it('组合过滤', () => {
    const result = useRequirementFilter(items, {
      dateFrom: '2026-01-01',
      dateTo: '2026-12-31',
      statuses: ['todo', 'deferred'],
      keyword: '模块',
    })
    expect(result).toHaveLength(2)
  })
})
