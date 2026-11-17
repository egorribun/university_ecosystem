import { useAuth } from "@/contexts/AuthContext"
import { useSessionIdentity } from "@/hooks/useSessionIdentity"
import { getConfirmedUserId } from "@/stores/authIdentity"

export function useConfirmedIdentityPending(): boolean {
  const { user, loading } = useAuth()
  const [, , sessionCurrent] = useSessionIdentity()
  return getConfirmedUserId({ user, loading: loading || sessionCurrent === false }) === null
}
