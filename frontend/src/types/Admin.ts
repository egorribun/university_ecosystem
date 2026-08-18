export interface FeatureFlag {
  name: string
  enabled: boolean
  default: boolean
  description: string
  provider: string
  evaluation_reason: string
  management: "gitops"
  config_path: string
}

export interface AuditLog {
  id: number
  actor_user_id?: number
  actor_name?: string
  subject_user_id?: number
  subject_name?: string
  resource_type: string
  resource_id?: string
  action: string
  context?: Record<string, unknown>
  ip_address?: string
  user_agent?: string
  created_at: string
  is_valid: boolean
}

export interface AuditLogList {
  items: AuditLog[]
  total: number
}
