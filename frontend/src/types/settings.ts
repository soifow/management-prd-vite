/**
 * 应用设置类型（与 Python management_prd.models.settings.AppSettings 契约一致）。
 *
 * 后端持久化在 storage_dir/settings.json，随数据目录一起迁移。
 */

export type ViewMode = 'module' | 'date'

/**
 * 项目列表「最新」日期的取值口径（与 Python AppSettings.project_list_date_mode 契约一致）。
 * - latest_any：最新需求日期（任意状态需求 date 取最大）
 * - latest_done：最新已完成日期（仅 done / ui_done_waiting_backend）
 * - latest_activity：最近操作时间（projects.updated_at）
 */
export type ProjectListDateMode = 'latest_any' | 'latest_done' | 'latest_activity'

export interface AppSettings {
  /** 启动默认聚合方式：module=按模块 / date=按时间 */
  default_view_mode: ViewMode
  /** 项目列表「最新」日期的取值口径 */
  project_list_date_mode: ProjectListDateMode
  /** 设置页分组 tab 的显示顺序（分组 key 数组） */
  settings_order: string[]
  /** 待办提醒：剩余天数阈值（含逾期）。仅剩余天数≤该值且未完成的需求进入待办 */
  reminder_threshold_days: number
  /** 待办提醒：紧急阈值（天）。剩余天数≤该值的聚合标题栏用紧急警告色 */
  urgent_threshold_days: number
  /** 待办提醒：当前提醒阈值内聚合标题栏的警告色（橙） */
  reminder_warning_color: string
  /** 待办提醒：紧急阈值内聚合标题栏的警告色（深红） */
  urgent_warning_color: string
  /** 无完成时限的未完成需求是否常驻待办列表 */
  show_no_deadline_in_todo: boolean
  /** 树形功能节点是否显示子需求进度 (done/total)；关则仅功能详情页显示 */
  show_subitem_progress_in_tree: boolean
  /** 是否启用智能导入（LLM 结构化解析） */
  llm_enabled: boolean
  /** LLM API 基础地址（OpenAI 兼容接口），如 https://api.deepseek.com/v1 */
  llm_base_url: string
  /** LLM API 密钥（本地明文存储） */
  llm_api_key: string
  /** LLM 模型名，如 deepseek-chat */
  llm_model: string
  /** LLM 请求超时（秒） */
  llm_timeout: number
  /** 导入备份自动清理保留数量（保留最近 N 个；schema 迁移备份永久保留不参与清理） */
  backup_retention_count: number
}
