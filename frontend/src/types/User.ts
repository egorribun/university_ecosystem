import type { components } from "@/api/generated/schema"

export type User = components["schemas"]["UserOut"] & {
  avatar_updated_at?: string
  avatar_version?: number
  updated_at?: string
}




