import { useEffect, useRef } from "react"
import { logWarning, logDebug, logError } from "@/app/logger"

/**
 * Global push subscription sync hook.
 * Should be called once in the app when user is authenticated.
 * Handles:
 * 1. Recovering push consent if localStorage was cleared but browser still has subscription
 * 2. Syncing push subscription with server on app load
 * 3. Re-syncing after login
 */
export function usePushSync(isAuthenticated: boolean) {
  const syncedRef = useRef(false)
  const lastAuthState = useRef(isAuthenticated)

  useEffect(() => {
    // Reset sync flag when auth state changes (user logged out then back in).
    if (lastAuthState.current !== isAuthenticated) {
      syncedRef.current = false
      lastAuthState.current = isAuthenticated
    }

    if (!isAuthenticated) return
    if (syncedRef.current) return

    let cancelled = false

    const syncPush = async () => {
      try {
        // Dynamically import to avoid loading push code when not needed
        const {
          isPushSupported,
          hasPushConsent,
          recoverPushConsentFromBrowser,
          softSyncPushSubscription,
        } = await import("@/push/subscribe")

        if (cancelled) return

        // Check if push is supported
        if (!isPushSupported()) {
          if (import.meta.env.DEV) logDebug("[usePushSync] Push not supported")
          return
        }
        if (typeof Notification === "undefined") {
          if (import.meta.env.DEV) logDebug("[usePushSync] Notification API undefined")
          return
        }

        // Try to recover consent if localStorage was cleared
        const recovered = await recoverPushConsentFromBrowser()

        if (cancelled) return

        const hasConsent = hasPushConsent()

        // If we have consent (either existing or recovered), sync the subscription
        if (recovered || hasConsent) {
          if (import.meta.env.DEV) logDebug("[usePushSync] Syncing subscription with server...")
          await softSyncPushSubscription()
          if (import.meta.env.DEV) logDebug("[usePushSync] Sync complete")
        } else {
          if (import.meta.env.DEV) logDebug("[usePushSync] No consent, skipping sync")
        }

        if (!cancelled) {
          syncedRef.current = true
        }
      } catch (error) {
        if (!cancelled) {
          logWarning("Failed to sync push subscription on app load", error)
          logError("[usePushSync] Error:", error)
        }
      }
    }

    // Small delay to avoid blocking initial render
    const timeoutId = setTimeout(() => {
      void syncPush()
    }, 100)

    return () => {
      cancelled = true
      clearTimeout(timeoutId)
    }
  }, [isAuthenticated])
}
