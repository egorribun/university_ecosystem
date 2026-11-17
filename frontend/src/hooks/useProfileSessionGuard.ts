import { useCallback, useEffect, useRef } from "react"
import { useAuth } from "@/contexts/AuthContext"
import { useIsomorphicLayoutEffect } from "@/hooks/useIsomorphicLayoutEffect"
import { useSessionIdentity } from "@/hooks/useSessionIdentity"
import { getConfirmedUserId } from "@/stores/authIdentity"
import { captureSessionEpoch, getBrowserSessionGeneration } from "@/stores/sessionEpoch"

/** A profile action belongs to both its initiating session and mounted account. */
export function useProfileSessionGuard() {
  const { user, loading } = useAuth()
  const userId = user?.id ?? null
  const [sessionEpoch, sessionGeneration] = useSessionIdentity()
  const lifetimeRef = useRef({ userId, active: false })
  const authRef = useRef({ user, loading })

  useEffect(() => {
    const lifetime = { userId, active: true }
    lifetimeRef.current = lifetime
    return () => {
      lifetime.active = false
    }
  }, [userId])

  // Child passive effects may dispatch immediately after identity settles.
  // Publish the committed snapshot before those effects run.
  useIsomorphicLayoutEffect(() => {
    authRef.current = { user, loading }
  }, [user, loading])

  return useCallback(() => {
    const lifetime = lifetimeRef.current
    // Same-account step-up loading preserves ownership; new actions still
    // require a confirmed identity at the moment they are dispatched.
    const confirmedUserId = getConfirmedUserId(authRef.current)
    const isSessionCurrent = captureSessionEpoch(sessionEpoch)
    return () =>
      confirmedUserId !== null &&
      lifetime.userId === userId &&
      lifetime.active &&
      getBrowserSessionGeneration() === sessionGeneration &&
      isSessionCurrent()
  }, [userId, sessionEpoch, sessionGeneration])
}
