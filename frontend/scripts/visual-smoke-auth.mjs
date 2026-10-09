const CSRF_COOKIE_NAMES = ["csrf_token", "_csrf_anon_nonce"]
const BROWSER_COOKIE_NAMES = ["access_token_v2", ...CSRF_COOKIE_NAMES]
const OWNED_SESSION_CLEANUP_FAILED = Symbol("owned-session-cleanup-failed")

export function getSetCookieHeaders(response) {
  if (typeof response?.headers?.getSetCookie === "function") {
    return response.headers.getSetCookie()
  }
  if (typeof response?.headers?.raw === "function") {
    return response.headers.raw()?.["set-cookie"] ?? []
  }
  const combined = response?.headers?.get?.("set-cookie")
  return typeof combined === "string" && combined !== "" ? [combined] : []
}

export function mergeSetCookieHeaders(seed, headers) {
  const cookies = new Map(seed)
  for (const header of headers) {
    const pair = header.split(";", 1)[0]
    const separator = pair.indexOf("=")
    if (separator <= 0) continue
    const name = pair.slice(0, separator).trim()
    const value = pair.slice(separator + 1).trim()
    if (value === "") cookies.delete(name)
    else cookies.set(name, value)
  }
  return cookies
}

export function cookieHeader(cookies, names) {
  return names
    .map((name) => {
      const value = cookies.get(name)
      if (typeof value !== "string" || value === "") {
        throw new Error(`Required cookie ${name} is missing`)
      }
      return `${name}=${value}`
    })
    .join("; ")
}

export async function fetchBoundCsrfCookies({ origin, fetchImpl = fetch }) {
  const response = await fetchImpl(`${origin}/api/v1/auth/csrf-cookie`)
  if (response.status !== 200) {
    throw new Error(`csrf-cookie failed: HTTP ${response.status}`)
  }
  const cookies = mergeSetCookieHeaders(new Map(), getSetCookieHeaders(response))
  try {
    cookieHeader(cookies, CSRF_COOKIE_NAMES)
  } catch {
    throw new Error("csrf-cookie must set csrf_token and _csrf_anon_nonce")
  }
  return cookies
}

export function playwrightCookies(cookies, originValue) {
  const origin = new URL(originValue)
  return BROWSER_COOKIE_NAMES.flatMap((name) => {
    const value = cookies.get(name)
    if (typeof value !== "string" || value === "") return []
    return [
      {
        name,
        value,
        domain: origin.hostname,
        path: "/",
        httpOnly: name !== "csrf_token",
        secure: origin.protocol === "https:",
        sameSite: "Lax",
      },
    ]
  })
}

function browserCookieMap(cookies) {
  return new Map(cookies.map(({ name, value }) => [name, value]))
}

function apiResponseSetCookieHeaders(response) {
  if (typeof response?.headersArray !== "function") return []
  try {
    return response
      .headersArray()
      .filter(({ name, value }) => name?.toLowerCase() === "set-cookie" && value)
      .map(({ value }) => value)
  } catch {
    return []
  }
}

function safeCookieValue(value) {
  return typeof value === "string" && value !== "" && !/[;\r\n]/u.test(value) ? value : undefined
}

function newlyIssuedAccessTokens(cookies, previousAccessTokens) {
  return new Set(
    cookies
      .filter(({ name }) => name === "access_token_v2")
      .map(({ value }) => safeCookieValue(value))
      .filter((value) => value && !previousAccessTokens.has(value))
  )
}

function newOwnedSession(cookies, previousAccessTokens, fallbackCookieJar) {
  const issuedTokens = newlyIssuedAccessTokens(cookies, previousAccessTokens)
  if (issuedTokens.size !== 1) return null

  const accessToken = [...issuedTokens][0]
  const cookieJar = browserCookieMap(cookies)
  if (safeCookieValue(cookieJar.get("access_token_v2")) !== accessToken) return null

  const session = {
    accessToken,
    csrfToken:
      safeCookieValue(cookieJar.get("csrf_token")) ??
      safeCookieValue(fallbackCookieJar.get("csrf_token")),
    anonymousNonce:
      safeCookieValue(cookieJar.get("_csrf_anon_nonce")) ??
      safeCookieValue(fallbackCookieJar.get("_csrf_anon_nonce")),
    cookieJar,
    cookies,
  }
  if (!session.csrfToken || !session.anonymousNonce) return null
  return session
}

function markOwnedSessionCleanupFailed(error) {
  if (error && typeof error === "object") {
    try {
      Object.defineProperty(error, OWNED_SESSION_CLEANUP_FAILED, { value: true })
    } catch {
      // The caller still receives the original failure; the cleanup attempt itself
      // has already failed closed.
    }
  }
  return error
}

export async function logoutOwnedBrowserSession({ context, origin, session }) {
  const accessToken = safeCookieValue(session?.accessToken)
  if (!accessToken) {
    throw new Error("Owned session revocation could not be verified")
  }

  let currentCookieJar = null
  try {
    currentCookieJar = browserCookieMap(await context.cookies(origin))
  } catch {
    // The retained bound pair remains a safe, exact-session fallback when the
    // browser cookie jar cannot be inspected during teardown.
  }
  const csrfToken = safeCookieValue(
    currentCookieJar ? currentCookieJar.get("csrf_token") : session?.csrfToken
  )
  const anonymousNonce = safeCookieValue(
    currentCookieJar ? currentCookieJar.get("_csrf_anon_nonce") : session?.anonymousNonce
  )
  if (!csrfToken || !anonymousNonce) {
    throw new Error("Owned session revocation could not be verified")
  }

  const cookies = new Map([
    ["access_token_v2", accessToken],
    ["csrf_token", csrfToken],
    ["_csrf_anon_nonce", anonymousNonce],
  ])
  try {
    const logoutResponse = await context.request.post(
      new URL("/api/v1/auth/logout", origin).toString(),
      {
        headers: {
          Cookie: cookieHeader(cookies, BROWSER_COOKIE_NAMES),
          "X-CSRF-Token": csrfToken,
        },
      }
    )
    if (logoutResponse.status() !== 200) {
      throw new Error("logout failed")
    }

    const revocationResponse = await context.request.get(
      new URL("/api/v1/users/me", origin).toString(),
      { headers: { Authorization: `Bearer ${accessToken}` } }
    )
    if (revocationResponse.status() !== 401) {
      throw new Error("revocation was not confirmed")
    }
  } catch {
    throw new Error("Owned session revocation could not be verified")
  }
}

async function recoverOwnedSessionAfterLogin(
  context,
  origin,
  previousTokens,
  fallbackJar,
  loginResponse
) {
  const responseJar = mergeSetCookieHeaders(
    new Map(fallbackJar),
    apiResponseSetCookieHeaders(loginResponse)
  )
  const responseCookies = [...responseJar].map(([name, value]) => ({ name, value }))
  const responseSession = newOwnedSession(responseCookies, previousTokens, fallbackJar)

  let cookies
  try {
    cookies = await context.cookies(origin)
  } catch {
    return {
      cookies: responseSession ? responseCookies : null,
      session: responseSession,
      readFailed: true,
      hasNewAccessToken:
        Boolean(responseSession) ||
        newlyIssuedAccessTokens(responseCookies, previousTokens).size > 0,
    }
  }

  let session = newOwnedSession(cookies, previousTokens, fallbackJar)
  if (session) return { cookies, session, readFailed: false, hasNewAccessToken: true }
  let hasNewAccessToken = newlyIssuedAccessTokens(cookies, previousTokens).size > 0

  try {
    cookies = await context.cookies(origin)
  } catch {
    return {
      cookies: responseSession ? responseCookies : null,
      session: responseSession,
      readFailed: true,
      hasNewAccessToken: hasNewAccessToken || Boolean(responseSession),
    }
  }
  session = newOwnedSession(cookies, previousTokens, fallbackJar)
  hasNewAccessToken ||= newlyIssuedAccessTokens(cookies, previousTokens).size > 0
  if (!session && responseSession) {
    return {
      cookies: responseCookies,
      session: responseSession,
      readFailed: false,
      hasNewAccessToken: true,
    }
  }
  return { cookies, session, readFailed: false, hasNewAccessToken }
}

export async function withOwnedSessionCleanup({
  browser,
  createContext,
  origin,
  run,
  onCleanupFailure = () => {},
}) {
  const contexts = []
  const ownedSessions = []
  const ownedContexts = new Set()
  let result
  let primaryError = null
  let hasPrimaryError = false

  async function createTrackedContext() {
    const context = await createContext()
    contexts.push(context)
    return context
  }

  function registerOwnedSession(context, session) {
    if (
      !contexts.includes(context) ||
      ownedContexts.has(context) ||
      !safeCookieValue(session?.accessToken) ||
      !safeCookieValue(session?.csrfToken) ||
      !safeCookieValue(session?.anonymousNonce)
    ) {
      throw new Error("Unable to track the owned browser session")
    }
    ownedContexts.add(context)
    ownedSessions.push({ context, session })
  }

  try {
    const context = await createTrackedContext()
    result = await run({
      context,
      ownSession: (session) => registerOwnedSession(context, session),
      async createOwnedContext() {
        const ownedContext = await createTrackedContext()
        return {
          context: ownedContext,
          ownSession: (session) => registerOwnedSession(ownedContext, session),
        }
      },
    })
  } catch (error) {
    hasPrimaryError = true
    primaryError = error
  }

  let cleanupFailed = Boolean(hasPrimaryError && primaryError?.[OWNED_SESSION_CLEANUP_FAILED])
  for (const { context, session } of ownedSessions) {
    try {
      await logoutOwnedBrowserSession({ context, origin, session })
    } catch {
      cleanupFailed = true
    }
  }

  for (const context of contexts) {
    try {
      await context.close()
    } catch {
      cleanupFailed = true
    }
  }
  try {
    await browser.close()
  } catch {
    cleanupFailed = true
  }

  if (cleanupFailed) {
    try {
      onCleanupFailure()
    } catch {
      // Cleanup status must not replace the original capture failure.
    }
  }
  if (hasPrimaryError) throw primaryError
  if (cleanupFailed) throw new Error("Authenticated browser cleanup failed")
  return result
}

export async function loginBrowserContext({ context, origin, email, password }) {
  const csrfResponse = await context.request.get(`${origin}/api/v1/auth/csrf-cookie`)
  if (csrfResponse.status() !== 200) {
    throw new Error(`csrf-cookie failed: HTTP ${csrfResponse.status()}`)
  }

  const csrfCookies = await context.cookies(origin)
  const csrfCookieJar = browserCookieMap(csrfCookies)
  const csrfToken = csrfCookieJar.get("csrf_token")
  cookieHeader(csrfCookieJar, CSRF_COOKIE_NAMES)
  const previousAccessTokens = new Set(
    csrfCookies
      .filter(({ name }) => name === "access_token_v2")
      .map(({ value }) => safeCookieValue(value))
      .filter(Boolean)
  )

  let loginResponse = null
  let loginRequestError = null
  try {
    loginResponse = await context.request.post(`${origin}/api/v1/auth/login/json`, {
      headers: {
        "Content-Type": "application/json",
        "X-CSRF-Token": csrfToken,
      },
      data: { email, password },
    })
  } catch (error) {
    loginRequestError = error
  }
  const loginStatus = loginResponse?.status() ?? null
  const recovered = await recoverOwnedSessionAfterLogin(
    context,
    origin,
    previousAccessTokens,
    csrfCookieJar,
    loginResponse
  )
  const loginFailure = loginRequestError
    ? new Error("Login request failed", { cause: loginRequestError })
    : new Error(`Login failed: HTTP ${loginStatus}`)
  if (loginStatus !== 200) {
    if (recovered.session) {
      try {
        await logoutOwnedBrowserSession({
          context,
          origin,
          session: recovered.session,
        })
      } catch {
        throw markOwnedSessionCleanupFailed(loginFailure)
      }
      throw loginFailure
    }
    if (recovered.readFailed || recovered.hasNewAccessToken) {
      throw markOwnedSessionCleanupFailed(loginFailure)
    }
    throw loginFailure
  }

  if (recovered.readFailed) {
    const error = new Error("Unable to verify login session cookies")
    if (recovered.session) {
      try {
        await logoutOwnedBrowserSession({
          context,
          origin,
          session: recovered.session,
        })
      } catch {
        throw markOwnedSessionCleanupFailed(error)
      }
      throw error
    }
    throw markOwnedSessionCleanupFailed(error)
  }
  if (!recovered.session) {
    const error = new Error("Unable to verify login session cookies")
    throw markOwnedSessionCleanupFailed(error)
  }

  // BrowserContext.request shares the browser's cookie jar and fingerprint.
  // Logging in through it prevents the auth session from being immediately
  // revoked when the first real page request uses Chromium's UA/language.
  return {
    cookies: recovered.cookies,
    cookieJar: browserCookieMap(recovered.cookies),
    ownedSession: recovered.session,
  }
}
