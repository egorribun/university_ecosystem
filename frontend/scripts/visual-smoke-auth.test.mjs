import assert from "node:assert/strict"
import { randomUUID } from "node:crypto"
import { readFile } from "node:fs/promises"
import test from "node:test"

const moduleUrl = new URL("./visual-smoke-auth.mjs", import.meta.url)

function response(status, cookies = []) {
  return {
    status,
    headers: { getSetCookie: () => cookies },
    async text() {
      return "response body"
    },
  }
}

async function captureRejection(action, matches) {
  let rejection
  await assert.rejects(action, (error) => {
    rejection = error
    return matches(error)
  })
  return rejection
}

test("CSRF bootstrap requires HTTP 200 and both bound cookies", async () => {
  const { fetchBoundCsrfCookies } = await import(moduleUrl)
  await assert.rejects(
    () =>
      fetchBoundCsrfCookies({
        origin: "http://localhost",
        fetchImpl: async () => response(503),
      }),
    /csrf-cookie failed: HTTP 503/u
  )
  for (const cookies of [
    ["csrf_token=token; Path=/"],
    ["_csrf_anon_nonce=nonce; Path=/; HttpOnly"],
  ]) {
    await assert.rejects(
      () =>
        fetchBoundCsrfCookies({
          origin: "http://localhost",
          fetchImpl: async () => response(200, cookies),
        }),
      /must set csrf_token and _csrf_anon_nonce/u
    )
  }
})

test("CSRF bootstrap calls the signed cookie endpoint and binds the login header", async () => {
  const { fetchBoundCsrfCookies, cookieHeader } = await import(moduleUrl)
  let requestedUrl
  const cookies = await fetchBoundCsrfCookies({
    origin: "http://localhost",
    fetchImpl: async (url) => {
      requestedUrl = url
      return response(200, [
        "csrf_token=token-v1; Path=/; SameSite=Lax",
        "_csrf_anon_nonce=nonce-v1; Path=/; HttpOnly; SameSite=Lax",
      ])
    },
  })

  assert.equal(requestedUrl, "http://localhost/api/v1/auth/csrf-cookie")
  assert.equal(
    cookieHeader(cookies, ["csrf_token", "_csrf_anon_nonce"]),
    "csrf_token=token-v1; _csrf_anon_nonce=nonce-v1"
  )
})

test("login cookie rotation overwrites changed cookies and preserves the bound nonce", async () => {
  const { mergeSetCookieHeaders, playwrightCookies } = await import(moduleUrl)
  const initial = new Map([
    ["csrf_token", "token-v1"],
    ["_csrf_anon_nonce", "nonce-v1"],
  ])
  const merged = mergeSetCookieHeaders(initial, [
    "access_token_v2=jwt; Path=/; HttpOnly",
    "csrf_token=token-v2; Path=/",
  ])

  assert.deepEqual(Object.fromEntries(merged), {
    csrf_token: "token-v2",
    _csrf_anon_nonce: "nonce-v1",
    access_token_v2: "jwt",
  })
  assert.deepEqual(
    playwrightCookies(merged, "https://university.example").map(({ name, value, secure }) => ({
      name,
      value,
      secure,
    })),
    [
      { name: "access_token_v2", value: "jwt", secure: true },
      { name: "csrf_token", value: "token-v2", secure: true },
      { name: "_csrf_anon_nonce", value: "nonce-v1", secure: true },
    ]
  )
})

test("browser-context login keeps CSRF and session fingerprint bound to Chromium", async () => {
  const { loginBrowserContext } = await import(moduleUrl)
  const requests = []
  let phase = "csrf"
  const context = {
    request: {
      async get(url) {
        requests.push({ method: "GET", url })
        return { status: () => 200, text: async () => "" }
      },
      async post(url, options) {
        requests.push({ method: "POST", url, options })
        phase = "login"
        return { status: () => 200, text: async () => "" }
      },
    },
    async cookies() {
      const bound = [
        { name: "csrf_token", value: "token-v1" },
        { name: "_csrf_anon_nonce", value: "nonce-v1" },
      ]
      return phase === "login"
        ? [...bound, { name: "access_token_v2", value: "signed-jwt" }]
        : bound
    },
  }

  const result = await loginBrowserContext({
    context,
    origin: "http://localhost",
    email: "student@example.test",
    password: "test-password", // pragma: allowlist secret
  })

  assert.equal(result.cookieJar.get("access_token_v2"), "signed-jwt")
  assert.equal(result.ownedSession.accessToken, "signed-jwt")
  assert.equal(result.ownedSession.csrfToken, "token-v1")
  assert.equal(result.ownedSession.anonymousNonce, "nonce-v1")
  assert.deepEqual(requests, [
    { method: "GET", url: "http://localhost/api/v1/auth/csrf-cookie" },
    {
      method: "POST",
      url: "http://localhost/api/v1/auth/login/json",
      options: {
        headers: { "Content-Type": "application/json", "X-CSRF-Token": "token-v1" },
        data: { email: "student@example.test", password: "test-password" }, // pragma: allowlist secret
      },
    },
  ])
})

test("owned session cleanup revokes each exact context token after capture completes", async () => {
  const { withOwnedSessionCleanup } = await import(moduleUrl)
  const calls = []
  const contexts = []
  const events = []
  let browserClosed = false
  const browser = {
    async close() {
      events.push("browser-close")
      browserClosed = true
    },
  }
  const session = () => ({
    accessToken: randomUUID(),
    csrfToken: randomUUID(),
    anonymousNonce: randomUUID(),
  })
  const sessions = [session(), session()]
  const createContext = async () => {
    const currentSession = sessions[contexts.length]
    const context = {
      closed: false,
      request: {
        async post(url, options) {
          calls.push({ method: "POST", url, options })
          events.push("logout")
          return { status: () => 200 }
        },
        async get(url, options) {
          calls.push({ method: "GET", url, options })
          events.push("verify")
          return { status: () => 401 }
        },
      },
      async close() {
        events.push("context-close")
        context.closed = true
      },
      async cookies() {
        return [
          { name: "csrf_token", value: currentSession.csrfToken },
          { name: "_csrf_anon_nonce", value: currentSession.anonymousNonce },
        ]
      },
    }
    contexts.push(context)
    return context
  }
  const [firstSession, secondSession] = sessions

  const result = await withOwnedSessionCleanup({
    browser,
    createContext,
    origin: "http://localhost",
    async run({ context, ownSession, createOwnedContext }) {
      ownSession(firstSession)
      const second = await createOwnedContext()
      second.ownSession(secondSession)
      assert.equal(context.closed, false)
      assert.equal(second.context.closed, false)
      assert.equal(browserClosed, false, "the browser must stay open through all captures")
      return "capture-complete"
    },
  })

  assert.equal(result, "capture-complete")
  assert.equal(contexts.length, 2)
  assert.ok(contexts.every(({ closed }) => closed))
  assert.equal(browserClosed, true)
  assert.deepEqual(
    calls.map(({ method, url }) => [method, url]),
    [
      ["POST", "http://localhost/api/v1/auth/logout"],
      ["GET", "http://localhost/api/v1/users/me"],
      ["POST", "http://localhost/api/v1/auth/logout"],
      ["GET", "http://localhost/api/v1/users/me"],
    ]
  )
  assert.equal(
    calls[0].options.headers.Cookie,
    `access_token_v2=${firstSession.accessToken}; csrf_token=${firstSession.csrfToken}; _csrf_anon_nonce=${firstSession.anonymousNonce}`
  )
  assert.equal(calls[1].options.headers.Authorization, `Bearer ${firstSession.accessToken}`)
  assert.equal(
    calls[2].options.headers.Cookie,
    `access_token_v2=${secondSession.accessToken}; csrf_token=${secondSession.csrfToken}; _csrf_anon_nonce=${secondSession.anonymousNonce}`
  )
  assert.equal(calls[3].options.headers.Authorization, `Bearer ${secondSession.accessToken}`)
  assert.ok(
    events.indexOf("browser-close") > events.lastIndexOf("verify"),
    "all owned sessions must be checked before the shared browser closes"
  )
})

test("session cleanup failures preserve the capture error and still close every resource", async () => {
  const { withOwnedSessionCleanup } = await import(moduleUrl)
  const primaryError = new Error("capture failed")
  const cleanupIndicators = []
  const closedContexts = []
  let browserClosed = false
  let logoutAttempts = 0
  const sessions = [ownedSession(), ownedSession()]
  let createdContexts = 0
  const browser = {
    async close() {
      browserClosed = true
    },
  }
  const createContext = async () => {
    const currentSession = sessions[createdContexts]
    createdContexts += 1
    const context = {
      request: {
        async post() {
          logoutAttempts += 1
          return { status: () => (logoutAttempts === 1 ? 503 : 200) }
        },
        async get() {
          return { status: () => 401 }
        },
      },
      async close() {
        closedContexts.push(context)
        throw new Error("context close failed")
      },
      async cookies() {
        return [
          { name: "csrf_token", value: currentSession.csrfToken },
          { name: "_csrf_anon_nonce", value: currentSession.anonymousNonce },
        ]
      },
    }
    return context
  }
  function ownedSession() {
    return {
      accessToken: randomUUID(),
      csrfToken: randomUUID(),
      anonymousNonce: randomUUID(),
    }
  }

  const thrown = await captureRejection(
    () =>
      withOwnedSessionCleanup({
        browser,
        createContext,
        origin: "http://localhost",
        onCleanupFailure(...details) {
          cleanupIndicators.push(details)
        },
        async run({ ownSession, createOwnedContext }) {
          ownSession(sessions[0])
          const second = await createOwnedContext()
          second.ownSession(sessions[1])
          throw primaryError
        },
      }),
    (error) => error === primaryError
  )

  assert.equal(thrown, primaryError)
  assert.equal(logoutAttempts, 2, "cleanup must continue after the first token fails")
  assert.equal(closedContexts.length, 2)
  assert.equal(browserClosed, true)
  assert.deepEqual(cleanupIndicators, [[]], "cleanup reporting must be separate and sanitized")
})

test("a pre-login failure closes resources without attempting logout", async () => {
  const { withOwnedSessionCleanup } = await import(moduleUrl)
  let logoutAttempts = 0
  let contextClosed = false
  let browserClosed = false
  await assert.rejects(
    () =>
      withOwnedSessionCleanup({
        browser: {
          async close() {
            browserClosed = true
          },
        },
        async createContext() {
          return {
            request: {
              async post() {
                logoutAttempts += 1
                return { status: () => 200 }
              },
            },
            async close() {
              contextClosed = true
            },
          }
        },
        origin: "http://localhost",
        async run() {
          throw new Error("login did not complete")
        },
      }),
    /login did not complete/u
  )
  assert.equal(logoutAttempts, 0)
  assert.equal(contextClosed, true)
  assert.equal(browserClosed, true)
})

test("login cookie inspection failure revokes response-issued session and reports cleanup failure safely", async () => {
  const { loginBrowserContext, withOwnedSessionCleanup } = await import(moduleUrl)

  for (const logoutStatus of [200, 503]) {
    const accessToken = randomUUID()
    const csrfToken = randomUUID()
    const anonymousNonce = randomUUID()
    const requests = []
    let cookieReads = 0
    let contextClosed = false
    let browserClosed = false
    const cleanupIndicators = []
    const context = {
      request: {
        async get(url, options) {
          requests.push({ method: "GET", url, options })
          return { status: () => (url.endsWith("/users/me") ? 401 : 200) }
        },
        async post(url, options) {
          requests.push({ method: "POST", url, options })
          if (url.endsWith("/auth/login/json")) {
            return {
              status: () => 200,
              headersArray: () => [
                { name: "set-cookie", value: `access_token_v2=${accessToken}; Path=/; HttpOnly` },
              ],
            }
          }
          return { status: () => logoutStatus }
        },
      },
      async cookies() {
        cookieReads += 1
        if (cookieReads === 1) {
          return [
            { name: "csrf_token", value: csrfToken },
            { name: "_csrf_anon_nonce", value: anonymousNonce },
          ]
        }
        throw new Error("cookie inspection unavailable")
      },
      async close() {
        contextClosed = true
      },
    }

    const thrown = await captureRejection(
      () =>
        withOwnedSessionCleanup({
          browser: {
            async close() {
              browserClosed = true
            },
          },
          async createContext() {
            return context
          },
          origin: "http://localhost",
          onCleanupFailure(...details) {
            cleanupIndicators.push(details)
          },
          async run({ context: currentContext }) {
            return loginBrowserContext({
              context: currentContext,
              origin: "http://localhost",
              email: "synthetic@example.test",
              password: randomUUID(),
            })
          },
        }),
      (error) => /Unable to verify login session cookies/u.test(error.message)
    )

    assert.equal(thrown.message, "Unable to verify login session cookies")
    const logout = requests.find(
      ({ method, url }) => method === "POST" && url.endsWith("/auth/logout")
    )
    assert.ok(logout, "response Set-Cookie must recover the exact session for cleanup")
    assert.equal(
      logout.options.headers.Cookie,
      `access_token_v2=${accessToken}; csrf_token=${csrfToken}; _csrf_anon_nonce=${anonymousNonce}`
    )
    if (logoutStatus === 200) {
      const verification = requests.find(
        ({ method, url }) => method === "GET" && url.endsWith("/users/me")
      )
      assert.equal(verification.options.headers.Authorization, `Bearer ${accessToken}`)
      assert.deepEqual(cleanupIndicators, [])
    } else {
      assert.deepEqual(cleanupIndicators, [[]])
    }
    assert.equal(contextClosed, true)
    assert.equal(browserClosed, true)
    assert.doesNotMatch(thrown.message, new RegExp(accessToken, "u"))
  }
})

test("a rejected login request still revokes its newly issued token with the current CSRF pair", async () => {
  const { loginBrowserContext, withOwnedSessionCleanup } = await import(moduleUrl)
  const accessToken = randomUUID()
  const originalCsrf = randomUUID()
  const originalNonce = randomUUID()
  const loginCsrf = randomUUID()
  const loginNonce = randomUUID()
  const rotatedCsrf = randomUUID()
  const rotatedNonce = randomUUID()
  const requestFailure = new Error("transport failed")
  const requests = []
  let cookieReads = 0
  let sessionCreated = false
  const context = {
    request: {
      async get(url, options) {
        requests.push({ method: "GET", url, options })
        return { status: () => (url.endsWith("/users/me") ? 401 : 200) }
      },
      async post(url, options) {
        requests.push({ method: "POST", url, options })
        if (url.endsWith("/auth/login/json")) {
          sessionCreated = true
          throw requestFailure
        }
        return { status: () => 200 }
      },
    },
    async cookies() {
      cookieReads += 1
      if (cookieReads === 1) {
        return [
          { name: "csrf_token", value: originalCsrf },
          { name: "_csrf_anon_nonce", value: originalNonce },
        ]
      }
      if (cookieReads === 2 && sessionCreated) {
        return [
          { name: "csrf_token", value: loginCsrf },
          { name: "_csrf_anon_nonce", value: loginNonce },
          { name: "access_token_v2", value: accessToken },
        ]
      }
      return [
        { name: "csrf_token", value: rotatedCsrf },
        { name: "_csrf_anon_nonce", value: rotatedNonce },
        { name: "access_token_v2", value: accessToken },
      ]
    },
    async close() {},
  }
  const cleanupIndicators = []

  const thrown = await captureRejection(
    () =>
      withOwnedSessionCleanup({
        browser: { async close() {} },
        async createContext() {
          return context
        },
        origin: "http://localhost",
        onCleanupFailure(...details) {
          cleanupIndicators.push(details)
        },
        async run({ context: currentContext }) {
          return loginBrowserContext({
            context: currentContext,
            origin: "http://localhost",
            email: "synthetic@example.test",
            password: randomUUID(),
          })
        },
      }),
    (error) => error.message === "Login request failed" && error.cause === requestFailure
  )

  assert.equal(thrown.message, "Login request failed")
  const logout = requests.find(
    ({ method, url }) => method === "POST" && url.endsWith("/auth/logout")
  )
  assert.equal(
    logout.options.headers.Cookie,
    `access_token_v2=${accessToken}; csrf_token=${rotatedCsrf}; _csrf_anon_nonce=${rotatedNonce}`
  )
  const revocationCheck = requests.find(
    ({ method, url }) => method === "GET" && url.endsWith("/users/me")
  )
  assert.equal(revocationCheck.options.headers.Authorization, `Bearer ${accessToken}`)
  assert.deepEqual(cleanupIndicators, [])
})

test("falsy thrown capture values remain failures after resource cleanup", async () => {
  const { withOwnedSessionCleanup } = await import(moduleUrl)
  let contextClosed = false
  let browserClosed = false
  const thrown = await captureRejection(
    () =>
      withOwnedSessionCleanup({
        browser: {
          async close() {
            browserClosed = true
          },
        },
        async createContext() {
          return {
            async close() {
              contextClosed = true
            },
          }
        },
        origin: "http://localhost",
        async run() {
          throw false
        },
      }),
    (error) => error === false
  )
  assert.equal(thrown, false)
  assert.equal(contextClosed, true)
  assert.equal(browserClosed, true)
})

test("login failure does not read or expose a response body that echoes the password", async () => {
  const { loginBrowserContext } = await import(moduleUrl)
  const echoMarker = "synthetic-body-echo-marker"
  let loginBodyRead = false
  const context = {
    request: {
      async get() {
        return { status: () => 200 }
      },
      async post() {
        return {
          status: () => 401,
          async text() {
            loginBodyRead = true
            return JSON.stringify({ detail: `Invalid credential: ${echoMarker}` })
          },
        }
      },
    },
    async cookies() {
      return [
        { name: "csrf_token", value: "csrf" },
        { name: "_csrf_anon_nonce", value: "nonce" },
      ]
    },
  }

  await assert.rejects(
    () =>
      loginBrowserContext({
        context,
        origin: "http://localhost",
        email: "admin@example.test",
        password: echoMarker,
      }),
    (error) => {
      assert.equal(error.message, "Login failed: HTTP 401")
      assert.doesNotMatch(error.message, new RegExp(echoMarker, "u"))
      return true
    }
  )
  assert.equal(loginBodyRead, false)
})

test("a failed login response revokes a newly issued exact session without a false cleanup alert", async () => {
  const { loginBrowserContext, withOwnedSessionCleanup } = await import(moduleUrl)
  const accessToken = randomUUID()
  const csrfToken = randomUUID()
  const anonymousNonce = randomUUID()
  const requests = []
  let cookieReads = 0
  const context = {
    request: {
      async get(url, options) {
        requests.push({ method: "GET", url, options })
        return { status: () => (url.endsWith("/users/me") ? 401 : 200) }
      },
      async post(url, options) {
        requests.push({ method: "POST", url, options })
        return { status: () => (url.endsWith("/auth/login/json") ? 401 : 200) }
      },
    },
    async cookies() {
      cookieReads += 1
      const cookies = [
        { name: "csrf_token", value: csrfToken },
        { name: "_csrf_anon_nonce", value: anonymousNonce },
      ]
      return cookieReads === 1
        ? cookies
        : [...cookies, { name: "access_token_v2", value: accessToken }]
    },
    async close() {},
  }
  const cleanupIndicators = []
  const thrown = await captureRejection(
    () =>
      withOwnedSessionCleanup({
        browser: { async close() {} },
        async createContext() {
          return context
        },
        origin: "http://localhost",
        onCleanupFailure(...details) {
          cleanupIndicators.push(details)
        },
        async run({ context: currentContext }) {
          return loginBrowserContext({
            context: currentContext,
            origin: "http://localhost",
            email: "synthetic@example.test",
            password: randomUUID(),
          })
        },
      }),
    (error) => /Login failed: HTTP 401/u.test(error.message)
  )

  assert.equal(thrown.message, "Login failed: HTTP 401")
  const logout = requests.find(
    ({ method, url }) => method === "POST" && url.endsWith("/auth/logout")
  )
  assert.equal(
    logout.options.headers.Cookie,
    `access_token_v2=${accessToken}; csrf_token=${csrfToken}; _csrf_anon_nonce=${anonymousNonce}`
  )
  assert.deepEqual(cleanupIndicators, [])
})

test("an HTTP 200 login without a recoverable token reports uncertain session cleanup", async () => {
  const { loginBrowserContext, withOwnedSessionCleanup } = await import(moduleUrl)
  const requests = []
  let cookieReads = 0
  let contextClosed = false
  let browserClosed = false
  const cleanupIndicators = []
  const csrfToken = randomUUID()
  const anonymousNonce = randomUUID()
  const context = {
    request: {
      async get(url, options) {
        requests.push({ method: "GET", url, options })
        return { status: () => (url.endsWith("/users/me") ? 401 : 200) }
      },
      async post(url, options) {
        requests.push({ method: "POST", url, options })
        return { status: () => 200, headersArray: () => [] }
      },
    },
    async cookies() {
      cookieReads += 1
      return [
        { name: "csrf_token", value: csrfToken },
        { name: "_csrf_anon_nonce", value: anonymousNonce },
      ]
    },
    async close() {
      contextClosed = true
    },
  }

  const thrown = await captureRejection(
    () =>
      withOwnedSessionCleanup({
        browser: {
          async close() {
            browserClosed = true
          },
        },
        async createContext() {
          return context
        },
        origin: "http://localhost",
        onCleanupFailure(...details) {
          cleanupIndicators.push(details)
        },
        async run({ context: currentContext }) {
          return loginBrowserContext({
            context: currentContext,
            origin: "http://localhost",
            email: "synthetic@example.test",
            password: randomUUID(),
          })
        },
      }),
    (error) => error.message === "Unable to verify login session cookies"
  )

  assert.equal(thrown.message, "Unable to verify login session cookies")
  assert.equal(cookieReads, 3)
  assert.deepEqual(
    requests.map(({ method, url }) => [method, new URL(url).pathname]),
    [
      ["GET", "/api/v1/auth/csrf-cookie"],
      ["POST", "/api/v1/auth/login/json"],
    ]
  )
  assert.deepEqual(cleanupIndicators, [[]])
  assert.equal(contextClosed, true)
  assert.equal(browserClosed, true)
})

test("a failed login that only observes a pre-existing token never revokes it", async () => {
  const { loginBrowserContext, withOwnedSessionCleanup } = await import(moduleUrl)
  const requests = []
  let cookieReads = 0
  const existingAccessToken = randomUUID()
  const csrfToken = randomUUID()
  const anonymousNonce = randomUUID()
  const cleanupIndicators = []
  const context = {
    request: {
      async get(url, options) {
        requests.push({ method: "GET", url, options })
        return { status: () => 200 }
      },
      async post(url, options) {
        requests.push({ method: "POST", url, options })
        return {
          status: () => (url.endsWith("/auth/login/json") ? 401 : 200),
          headersArray: () => [],
        }
      },
    },
    async cookies() {
      cookieReads += 1
      return [
        { name: "csrf_token", value: csrfToken },
        { name: "_csrf_anon_nonce", value: anonymousNonce },
        { name: "access_token_v2", value: existingAccessToken },
      ]
    },
    async close() {},
  }

  const thrown = await captureRejection(
    () =>
      withOwnedSessionCleanup({
        browser: { async close() {} },
        async createContext() {
          return context
        },
        origin: "http://localhost",
        onCleanupFailure(...details) {
          cleanupIndicators.push(details)
        },
        async run({ context: currentContext }) {
          return loginBrowserContext({
            context: currentContext,
            origin: "http://localhost",
            email: "synthetic@example.test",
            password: randomUUID(),
          })
        },
      }),
    (error) => error.message === "Login failed: HTTP 401"
  )

  assert.equal(thrown.message, "Login failed: HTTP 401")
  assert.equal(cookieReads, 3)
  assert.deepEqual(
    requests.map(({ method, url }) => [method, new URL(url).pathname]),
    [
      ["GET", "/api/v1/auth/csrf-cookie"],
      ["POST", "/api/v1/auth/login/json"],
    ]
  )
  assert.equal(
    requests.some(({ options }) =>
      [options?.headers?.Cookie, options?.headers?.Authorization].some((value) =>
        value?.includes(existingAccessToken)
      )
    ),
    false
  )
  assert.deepEqual(cleanupIndicators, [])
})

test("authenticated and admin smoke scripts use browser-context login exclusively", async () => {
  for (const script of ["authenticated-visual-audit.mjs", "admin-visual-smoke.mjs"]) {
    const source = await readFile(new URL(script, import.meta.url), "utf8")
    assert.match(source, /loginBrowserContext/u)
    assert.match(source, /await withOwnedSessionCleanup\(/u)
    assert.doesNotMatch(source, /fetch\(`\$\{ORIGIN\}\/api\/v1\/auth\/login\/json/u)

    const addCookiesCalls = [...source.matchAll(/\.addCookies\s*\(/gu)]
    const expectsPreferenceCookies = script === "authenticated-visual-audit.mjs"

    if (expectsPreferenceCookies) {
      assert.equal(addCookiesCalls.length, 1)
      const preferenceFunction = source.match(
        /async function setStudentCapturePreferences\(context, captureConfig\) \{([\s\S]*?)\n\}/u
      )
      assert.ok(preferenceFunction, "student preference-cookie setter must remain identifiable")
      assert.match(
        preferenceFunction[1],
        /^\s*const origin = new URL\(ORIGIN\)\s+await context\.addCookies\(\s*\[\s*\{\s*name:\s*"ue:language",\s*value:\s*captureConfig\.locale\s*\},\s*\{\s*name:\s*"ue-mode",\s*value:\s*captureConfig\.theme\s*\},?\s*\]\.map\(\(\{\s*name,\s*value\s*\}\)\s*=>\s*\(\{\s*name,\s*value,\s*domain:\s*origin\.hostname,\s*path:\s*"\/",\s*secure:\s*origin\.protocol\s*===\s*"https:",\s*sameSite:\s*"Lax",?\s*\}\)\)\s*\)\s*$/u
      )
    } else {
      assert.equal(addCookiesCalls.length, 2)
      for (const [functionName, cookieShape] of [
        [
          "setSmokeTheme",
          /await page\.context\(\)\.addCookies\(\s*\[\s*\{\s*name:\s*"ue-mode",\s*value:\s*theme,\s*domain:\s*cookieDomain,\s*path:\s*"\/",?\s*\},?\s*\]\s*\)/u,
        ],
        [
          "setSmokeLocale",
          /await page\.context\(\)\.addCookies\(\s*\[\s*\{\s*name:\s*"ue:language",\s*value:\s*locale,\s*domain:\s*origin\.hostname,\s*path:\s*"\/",\s*secure:\s*origin\.protocol\s*===\s*"https:",\s*sameSite:\s*"Lax",?\s*\},?\s*\]\s*\)/u,
        ],
      ]) {
        const preferenceFunction = source.match(
          new RegExp(`async function ${functionName}\\([\\s\\S]*?\\n\\}`, "u")
        )
        assert.ok(preferenceFunction, `${functionName} must remain identifiable`)
        assert.equal(
          [...preferenceFunction[0].matchAll(/\.addCookies\s*\(/gu)].length,
          1,
          `${functionName} must add exactly one preference cookie`
        )
        assert.match(preferenceFunction[0], cookieShape)
      }
    }
  }
})

test("authenticated audit fails closed on axe and transport execution errors", async () => {
  const source = await readFile(new URL("authenticated-visual-audit.mjs", import.meta.url), "utf8")

  assert.match(source, /page\.on\("requestfailed", requestFailedHandler\)/u)
  assert.match(source, /classifyAuthenticatedAuditSummaries/u)
  assert.match(source, /classifyAuthenticatedAuditSummaries\(summaries\)/u)
  assert.match(source, /if \(axeErrors\.length > 0\)/u)
  assert.match(source, /if \(axeTimeout\) clearTimeout\(axeTimeout\)/u)
})
