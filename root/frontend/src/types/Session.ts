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
  is_current: boolean
}
