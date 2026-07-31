/** 模块一等实体（与后端 models/module.py 契约一致）。 */
export interface Module {
  id: string
  project_id: string
  name: string
  created_at: string
  updated_at: string
}
