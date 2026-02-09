import type { components } from "@/api/generated/schema"

export type PushSubscriptionResponse = components["schemas"]["PushSubscriptionOut"]
export type SendTestNotificationResponse = components["schemas"]["SendTestResponse"]

export type PushTopicsResponse = {
  allowed: string[]
  topics: string[]
  has_preferences?: boolean
  updated_at?: string | null
}

export type AdminUserTopicsResponse = {
  user_id: string
  email: string
  topics: string[]
  allowed_topics: string[]
  updated_at?: string | null
}




