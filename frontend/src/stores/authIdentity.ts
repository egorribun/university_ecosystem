import type { UserState } from "@/types/Auth"
import { useAuthStore } from "./useAuthStore"

/** Role-only user rendered from the SSR auth hint before `/users/me` resolves. */
export const SSR_STUB_USER_ID = "ssr-stub"
/** Render-only user shown while the encrypted profile cache is decrypted. */
export const ENCRYPTED_CACHE_PLACEHOLDER_USER_ID = "-1"
/** Prefix of the synthetic identities used by Lighthouse audit builds. */
export const LHCI_USER_ID_PREFIX = "lhci-"

const DEFAULT_CONFIRMATION_TIMEOUT_MS = 15_000

type AuthIdentitySnapshot = {
  user: UserState
  loading: boolean
}

/**
 * Returns the authenticated user id only once auth hydration has settled on a
 * real account. Placeholder identities published during SSR hydration, cache
 * decryption, or Lighthouse runs never count as confirmed, and the profile
 * cache is deliberately not consulted.
 */
export function getConfirmedUserId({ user, loading }: AuthIdentitySnapshot): string | null {
  if (loading) return null
  const rawId: unknown = user?.id
  if (typeof rawId !== "string" && typeof rawId !== "number") return null
  const id = String(rawId).trim()
  if (
    !id ||
    id === SSR_STUB_USER_ID ||
    id === ENCRYPTED_CACHE_PLACEHOLDER_USER_ID ||
    id.startsWith(LHCI_USER_ID_PREFIX)
  ) {
    return null
  }
  return id
}

type WaitForConfirmedUserIdOptions = {
  expectedUserId?: string
  timeoutMs?: number
}

/**
 * Resolves the confirmed user id as soon as auth settles on a real account.
 * Resolves `null` when auth settles signed out, when a different account than
 * `expectedUserId` is confirmed, or when `timeoutMs` elapses first.
 */
export function waitForConfirmedUserId({
  expectedUserId,
  timeoutMs = DEFAULT_CONFIRMATION_TIMEOUT_MS,
}: WaitForConfirmedUserIdOptions = {}): Promise<string | null> {
  // `undefined` means "not settled yet"; `null` is a settled negative answer.
  const settledIdentity = (state: AuthIdentitySnapshot): string | null | undefined => {
    const confirmed = getConfirmedUserId(state)
    if (confirmed !== null) {
      return expectedUserId === undefined || confirmed === expectedUserId ? confirmed : null
    }
    return !state.loading && state.user === null ? null : undefined
  }

  const initial = settledIdentity(useAuthStore.getState())
  if (initial !== undefined) return Promise.resolve(initial)

  return new Promise((resolve) => {
    const settle = (value: string | null) => {
      clearTimeout(timer)
      unsubscribe()
      resolve(value)
    }
    const timer = setTimeout(() => settle(null), timeoutMs)
    const unsubscribe = useAuthStore.subscribe((state) => {
      const identity = settledIdentity(state)
      if (identity !== undefined) settle(identity)
    })
  })
}
