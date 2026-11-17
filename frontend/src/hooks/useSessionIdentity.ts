import { useSyncExternalStore } from "react"
import {
  getServerSessionIdentitySnapshot,
  getSessionIdentitySnapshot,
  subscribeSessionIdentity,
} from "@/stores/sessionEpoch"

type SessionIdentity = readonly [epoch: number, generation: string | null, current: boolean | null]

/** Observe session changes even when the authenticated user object is unchanged. */
export function useSessionIdentity(): SessionIdentity {
  const snapshot = useSyncExternalStore(
    subscribeSessionIdentity,
    getSessionIdentitySnapshot,
    getServerSessionIdentitySnapshot
  )
  return JSON.parse(snapshot) as SessionIdentity
}
