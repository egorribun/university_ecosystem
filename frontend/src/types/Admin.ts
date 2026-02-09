export type FlagStatus = "enabled" | "disabled" | "percentage"

export interface FeatureFlag {
  name: string
  status: FlagStatus
  description: string
  percentage: number
  allowed_users: number[]
  allowed_groups: string[]
  metadata: Record<string, any>
}

export interface FeatureFlagUpdatePayload {
  status?: FlagStatus
  percentage?: number
  description?: string
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
  context?: Record<string, any>
  ip_address?: string
  user_agent?: string
  created_at: string
  is_valid: boolean
}

export interface AuditLogList {
  items: AuditLog[]
  total: number
}




