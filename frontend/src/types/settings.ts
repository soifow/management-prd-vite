/**
 * 应用设置类型（与 Python management_prd.models.settings.AppSettings 契约一致）。
 *
 * 后端持久化在 storage_dir/settings.json，随数据目录一起迁移。
 */

export type ViewMode = 'module' | 'date'

export interface AppSettings {
  /** 启动默认聚合方式：module=按模块 / date=按时间 */
  default_view_mode: ViewMode
}
