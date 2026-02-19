// Deprecated: Auth is now cookie-only (HttpOnly).
// These functions are kept for compatibility but are no-ops.

export const ACCESS_TOKEN_STORAGE_KEY = "ecosystem.access.token"

export const readAccessToken = (): string | null => {
  return null
}

export const persistAccessToken = (_token: string | null | undefined) => {
  // No-op
}

export const clearAccessToken = () => {
  // No-op
}
