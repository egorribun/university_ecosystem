import { useAuth } from "@/contexts/AuthContext"
import { getConfirmedUserId } from "@/stores/authIdentity"

export function useConfirmedIdentityPending(): boolean {
  const { user, loading } = useAuth()
  return getConfirmedUserId({ user, loading }) === null
}
