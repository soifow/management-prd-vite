/**
 * 前后端通信的错误信封（后端 _err() 返回的形态）。
 *
 * 成功时 WebApi 方法返回业务数据；失败时返回 { success: false, error }。
 */

export interface ApiErrorEnvelope {
  success: false
  error: string
}

/** 类型守卫：判断值是否为错误信封。 */
export function isApiErrorEnvelope(value: unknown): value is ApiErrorEnvelope {
  return (
    typeof value === 'object' &&
    value !== null &&
    (value as { success?: unknown }).success === false &&
    typeof (value as { error?: unknown }).error === 'string'
  )
}

/** 存储位置信息（get_storage_info / migrate_storage 返回）。 */
export interface StorageInfo {
  /** 当前数据存储目录绝对路径 */
  storage_dir: string
  /** 是否使用默认位置（未自定义） */
  is_default: boolean
}

/** 导入前备份清单条目（list_import_backups 返回，manifest.json 元信息）。 */
export interface ImportBackupEntry {
  /** 备份 id（manifest 条目 id，用于回滚/删除） */
  id: string
  /** 备份文件名（requment.db.preimport.{YYYYMMDD-HHMMSS}.bak） */
  file: string
  /** 备份创建时间 ISO（如 2026-08-04T10:15:30） */
  created_at: string
  /** 触发来源：import=基础导入 / smart_import=智能导入 */
  trigger: 'import' | 'smart_import'
  /** 来源描述（快照项目名 / 模型名等） */
  source: string
  /** 目标项目 id（导入到已有项目时；新建项目为 null） */
  project_id: string | null
  /** 目标项目名（导入到已有项目时为 null） */
  project_name: string | null
  /** 备份文件大小（字节） */
  size: number
}
