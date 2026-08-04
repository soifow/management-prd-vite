import { describe, expect, it } from 'vitest'

import { moveKey, normalizeOrder } from '../settingsOrder'

const ALL_KEYS = ['storage', 'display', 'reminder', 'subitem'] as const

describe('normalizeOrder', () => {
  it('保留完整顺序数组原样', () => {
    const base = ['storage', 'display', 'reminder', 'subitem']
    expect(normalizeOrder(base, ALL_KEYS)).toEqual(base)
  })

  it('补齐缺失的 key（无法重排的根因修复）：缺失的追加到末尾', () => {
    // 旧版本持久化的 settings_order 只含 storage/display，reminder/subitem 缺失
    const base = ['storage', 'display']
    expect(normalizeOrder(base, ALL_KEYS)).toEqual(['storage', 'display', 'reminder', 'subitem'])
  })

  it('缺失 key 在任意位置都补齐到末尾', () => {
    expect(normalizeOrder(['reminder'], ALL_KEYS)).toEqual([
      'reminder',
      'storage',
      'display',
      'subitem',
    ])
  })

  it('过滤未知 key 并去重', () => {
    const base = ['storage', 'bogus', 'display', 'storage', 'reminder']
    expect(normalizeOrder(base, ALL_KEYS)).toEqual(['storage', 'display', 'reminder', 'subitem'])
  })

  it('空数组补齐全部 key', () => {
    expect(normalizeOrder([], ALL_KEYS)).toEqual(['storage', 'display', 'reminder', 'subitem'])
  })

  it('未来新增分组自动纳入（注册顺序在前、缺失补末尾）', () => {
    const future = ['storage', 'display', 'reminder', 'subitem', 'theme'] as const
    expect(normalizeOrder(['storage', 'subitem'], future)).toEqual([
      'storage',
      'subitem',
      'display',
      'reminder',
      'theme',
    ])
  })
})

describe('moveKey', () => {
  it('向下拖（reminder → subitem）：reminder 移到 subitem 之后', () => {
    const base = ['storage', 'display', 'reminder', 'subitem']
    expect(moveKey(base, 'reminder', 'subitem')).toEqual([
      'storage',
      'display',
      'subitem',
      'reminder',
    ])
  })

  it('向上拖（subitem → reminder）：subitem 移到 reminder 之前', () => {
    const base = ['storage', 'display', 'reminder', 'subitem']
    expect(moveKey(base, 'subitem', 'reminder')).toEqual([
      'storage',
      'display',
      'subitem',
      'reminder',
    ])
  })

  it('reminder 上移到 display（首 target）', () => {
    const base = ['storage', 'display', 'reminder', 'subitem']
    expect(moveKey(base, 'reminder', 'display')).toEqual([
      'storage',
      'reminder',
      'display',
      'subitem',
    ])
  })

  it('任意重排：storage 移到末尾', () => {
    const base = ['storage', 'display', 'reminder', 'subitem']
    expect(moveKey(base, 'storage', 'subitem')).toEqual([
      'display',
      'reminder',
      'subitem',
      'storage',
    ])
  })

  it('相同 key 或缺失 key 原样返回', () => {
    const base = ['storage', 'display', 'reminder', 'subitem']
    expect(moveKey(base, 'reminder', 'reminder')).toEqual(base)
    expect(moveKey(base, 'bogus', 'reminder')).toEqual(base)
    expect(moveKey(base, 'reminder', 'bogus')).toEqual(base)
  })

  it('不修改入参数组', () => {
    const base = ['storage', 'display', 'reminder', 'subitem']
    moveKey(base, 'reminder', 'subitem')
    expect(base).toEqual(['storage', 'display', 'reminder', 'subitem'])
  })
})