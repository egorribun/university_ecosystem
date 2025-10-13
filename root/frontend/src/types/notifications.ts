export type PushSubscriptionResponse = {
  id: number
  user_id: number
  endpoint: string
  p256dh: string
  auth: string
  created_at: string
  user_agent?: string | null
  last_seen_at?: string | null
  updated_at?: string | null
  topics: string[]
}

export type SendTestNotificationResponse = {
  sent: number
  removed: number
  failed: number
  detail?: string | null
}
