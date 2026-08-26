const CSRF_COOKIE_NAMES = ["csrf_token", "_csrf_anon_nonce"]
const BROWSER_COOKIE_NAMES = ["access_token_v2", ...CSRF_COOKIE_NAMES]

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
    const body = typeof response.text === "function" ? await response.text() : ""
    throw new Error(`csrf-cookie failed: HTTP ${response.status} — ${body.slice(0, 200)}`)
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

export async function loginBrowserContext({ context, origin, email, password }) {
  const csrfResponse = await context.request.get(`${origin}/api/v1/auth/csrf-cookie`)
  if (csrfResponse.status() !== 200) {
    const body = await csrfResponse.text()
    throw new Error(`csrf-cookie failed: HTTP ${csrfResponse.status()} — ${body.slice(0, 200)}`)
  }

  let cookies = await context.cookies(origin)
  let cookieJar = browserCookieMap(cookies)
  const csrfToken = cookieJar.get("csrf_token")
  cookieHeader(cookieJar, CSRF_COOKIE_NAMES)

  const loginResponse = await context.request.post(`${origin}/api/v1/auth/login/json`, {
    headers: {
      "Content-Type": "application/json",
      "X-CSRF-Token": csrfToken,
    },
    data: { email, password },
  })
  if (loginResponse.status() !== 200) {
    const body = await loginResponse.text()
    throw new Error(`Login failed: HTTP ${loginResponse.status()} — ${body.slice(0, 200)}`)
  }

  // BrowserContext.request shares the browser's cookie jar and fingerprint.
  // Logging in through it prevents the auth session from being immediately
  // revoked when the first real page request uses Chromium's UA/language.
  cookies = await context.cookies(origin)
  cookieJar = browserCookieMap(cookies)
  if (!cookieJar.get("access_token_v2")) {
    throw new Error("access_token_v2 cookie not in login response")
  }
  return { cookies, cookieJar }
}
