import type { RequirementStatus } from './requirement'

/** 导入预览需求（前端可编辑 selected/status）。v3：单 date。 */
export interface ParsedRequirement {
  module: string
  feature: string
  content: string
  status: RequirementStatus
  date: string // ISO yyyy-MM-dd
  selected: boolean
}

/** pick_and_parse_import 返回结果：解析出的需求 + 文件名（去扩展名）。 */
export interface PickParseResult {
  requirements: ParsedRequirement[]
  filename: string
}
