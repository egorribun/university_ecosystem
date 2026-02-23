import type { UserOut } from "@/api/generated"

export type User = UserOut & {
  avatar_updated_at?: string
  avatar_version?: number
  updated_at?: string
}
