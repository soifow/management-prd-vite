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
