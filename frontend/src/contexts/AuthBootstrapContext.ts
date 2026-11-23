import {
  CancelledError,
  onlineManager,
  type QueryClient,
  type QueryKey,
} from "@tanstack/react-query"
import { createContext, useCallback, useContext, useRef, useSyncExternalStore } from "react"
import { useIsomorphicLayoutEffect } from "@/hooks/useIsomorphicLayoutEffect"

/** The initial profile/key request is still settling in the surrounding provider. */
export const AuthBootstrapContext = createContext(false)

export type CommittedAuthBootstrap = { pending: boolean; active: boolean }
/** Shared by all observers belonging to one mounted AuthProvider. */
export const CommittedAuthBootstrapContext = createContext<{
  current: CommittedAuthBootstrap
} | null>(null)

/** Standalone consumers retain their existing behavior outside an auth provider. */
export const useAuthBootstrapPending = () => useContext(AuthBootstrapContext)

const getOnlineSnapshot = () => onlineManager.isOnline()
const getServerOnlineSnapshot = () => true

/** Keep an offline-first cached list usable while its owner bootstraps. */
export function useAuthBootstrapQueryGate(client: QueryClient, queryKey: QueryKey) {
  const pending = useAuthBootstrapPending()
  const shared = useContext(CommittedAuthBootstrapContext)
  const standalone = useRef<CommittedAuthBootstrap>({ pending, active: true })
  useIsomorphicLayoutEffect(() => {
    standalone.current.pending = pending
  }, [pending])
  const committed = shared ?? standalone
  const subscribe = useCallback(
    (notify: () => void) => {
      if (!pending) return () => undefined
      return onlineManager.subscribe((online) => {
        if (online) {
          const query = client.getQueryCache().find({ queryKey, exact: true })
          // Preserve exactly the observer's normal reconnect policy.
          if (query?.observers.some((observer) => observer.shouldFetchOnReconnect())) {
            void client.invalidateQueries({ queryKey, exact: true, refetchType: "none" })
          }
        }
        notify()
      })
    },
    [client, pending, queryKey]
  )
  const online = useSyncExternalStore(subscribe, getOnlineSnapshot, getServerOnlineSnapshot)
  const cancelIfBlocked = useCallback(() => {
    if (
      typeof window === "undefined" ||
      (committed.current.active && (!committed.current.pending || !onlineManager.isOnline()))
    )
      return
    // Query's reconnect can resume before React applies the disabled state.
    void client.cancelQueries({ queryKey, exact: true })
    void client.invalidateQueries({ queryKey, exact: true, refetchType: "none" })
    throw new CancelledError({ revert: true })
  }, [client, committed, queryKey])
  return { blocked: pending && online, cancelIfBlocked }
}
