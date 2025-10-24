export interface ActiveSession {
  id: number
  user_id: number
  jti: string
  created_at: string
  expires_at: string
  revoked_at: string | null
  ip_address: string | null
  user_agent: string | null
  last_seen_at: string | null
  mfa_required: boolean
  mfa_completed_at: string | null
  mfa_method: string | null
  mfa_verified_at: string | null
  is_current: boolean
}
