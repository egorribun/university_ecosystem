export const ACCESS_TOKEN_STORAGE_KEY = "ecosystem.access.token"

export const readAccessToken = (): string | null => {
  if (typeof sessionStorage === "undefined") return null
  try {
    return sessionStorage.getItem(ACCESS_TOKEN_STORAGE_KEY)
  } catch {
    return null
  }
}

export const persistAccessToken = (token: string | null | undefined) => {
  if (typeof sessionStorage === "undefined") return
  try {
    if (token) {
      sessionStorage.setItem(ACCESS_TOKEN_STORAGE_KEY, token)
    } else {
      sessionStorage.removeItem(ACCESS_TOKEN_STORAGE_KEY)
    }
  } catch {
    /* ignore */
  }
}

export const clearAccessToken = () => {
  persistAccessToken(null)
}




