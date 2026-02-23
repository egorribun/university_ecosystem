import type {
  AdminUserTopicsResponse,
  PushSubscriptionOut,
  SendTestResponse,
} from "@/api/generated"

export type PushSubscriptionResponse = PushSubscriptionOut
export type SendTestNotificationResponse = SendTestResponse

export type PushTopicsResponse = {
  allowed: string[]
  topics: string[]
  has_preferences?: boolean
  updated_at?: string | null
}

export type { AdminUserTopicsResponse }
