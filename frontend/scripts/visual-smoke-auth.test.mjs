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

test("authenticated audit pins only the weather host; seeded media is served by the stand", async () => {
  const source = await readFile(new URL("authenticated-visual-audit.mjs", import.meta.url), "utf8")

  assert.doesNotMatch(source, /picsum|PINNED_EXTERNAL_IMAGE/u)
  const routeCalls = [...source.matchAll(/\b(?:context|page|routePage)\.route\s*\(/gu)]
  assert.equal(routeCalls.length, 1, "the audit installs exactly the weather route")

  const { summarizeAuthenticatedVisualDiagnostics } =
    await import("./authenticated-visual-audit.mjs")
  const externalOutage = summarizeAuthenticatedVisualDiagnostics({
    httpFailures: [
      { method: "GET", url: "https://tiles.openfreemap.org/planet.pbf", status: 503 },
      { method: "GET", url: "https://example.invalid/cover.png", status: 500 },
    ],
  })
  assert.equal(externalOutage.httpStatusClassCounts["5xx"], 2)
  assert.equal(externalOutage.httpFailureOriginCounts.external, 2)
})

test("authenticated audit answers only the Open-Meteo forecast endpoint with a pinned forecast", async () => {
  const source = await readFile(new URL("authenticated-visual-audit.mjs", import.meta.url), "utf8")

  // Exactly the forecast endpoint the dashboard calls; no other weather or tile host.
  assert.match(
    source,
    /const PINNED_WEATHER_ROUTE = "https:\/\/api\.open-meteo\.com\/v1\/forecast\*\*"/u
  )
  const weatherClient = await readFile(new URL("../src/api/weather.ts", import.meta.url), "utf8")
  assert.match(weatherClient, /new URL\("https:\/\/api\.open-meteo\.com\/v1\/forecast"\)/u)

  const weatherRouteIndex = source.indexOf("await context.route(PINNED_WEATHER_ROUTE")
  const newPageIndex = source.indexOf("const page = await context.newPage()")
  const fulfil = source.slice(weatherRouteIndex, newPageIndex)
  assert.match(fulfil, /status:\s*200/u)
  assert.match(fulfil, /contentType:\s*"application\/json"/u)
  // The page fetches cross-origin, so the pinned answer must pass the CORS check.
  assert.match(fulfil, /headers:\s*\{\s*"access-control-allow-origin":\s*"\*"\s*\}/u)
  assert.match(fulfil, /body:\s*pinnedWeatherForecast/u)

  // The pinned forecast carries every current field the product reads.
  const start = source.indexOf("const pinnedWeatherForecast = JSON.stringify(")
  const end = source.indexOf("await context.route(PINNED_WEATHER_ROUTE", start)
  const declaration = source.slice(start, end)
  for (const field of [
    "temperature_2m",
    "weather_code",
    "is_day",
    "apparent_temperature",
    "wind_speed_10m",
    "relative_humidity_2m",
    "uv_index",
  ]) {
    assert.match(declaration, new RegExp(`\\b${field}:`, "u"), field)
  }
  assert.match(source, /externalWeatherFixture:\s*\{\s*route:\s*PINNED_WEATHER_ROUTE,/u)
})

// Include authenticated capture diagnostics in the existing hosted visual contract lane.
import "./authenticated-visual-runtime-diagnostic.test.mjs"

async function withVisualRequestDiagnostics(run) {
  const previousArg = process.argv[1]
  const previousOrigin = process.env.ORIGIN
  const previousMatrix = process.env.VISUAL_CAPTURE_MATRIX
  const previousLog = console.log
  const lines = []
  process.argv[1] = "frontend/scripts/authenticated-visual-audit.mjs"
  process.env.ORIGIN = "https://stand.invalid"
  process.env.VISUAL_CAPTURE_MATRIX = "1"
  console.log = (line) => lines.push(line)
  try {
    const module = await import(`./visual-smoke-contract.mjs?diagnostics=${randomUUID()}`)
    await run(module, lines)
  } finally {
    process.argv[1] = previousArg
    if (previousOrigin === undefined) delete process.env.ORIGIN
    else process.env.ORIGIN = previousOrigin
    if (previousMatrix === undefined) delete process.env.VISUAL_CAPTURE_MATRIX
    else process.env.VISUAL_CAPTURE_MATRIX = previousMatrix
    console.log = previousLog
  }
}

function visualFailure(url, errorText, route = "/dashboard", width = 1440) {
  return {
    method: () => "GET",
    url: () => url,
    failure: () => ({ errorText }),
    frame: () => ({
      page: () => ({
        url: () => `https://stand.invalid${route}`,
        viewportSize: () => ({ width, height: 900 }),
      }),
    }),
  }
}

test("visual request diagnostics project closed browser errors and same-origin API families", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    const cases = [
      [
        "https://stand.invalid/api/v1/events?token=private-marker",
        "net::ERR_HTTP2_PROTOCOL_ERROR",
        "events",
        "http2_protocol_error",
      ],
      [
        "https://stand.invalid/api/v1/news?token=private-marker",
        "net::ERR_EMPTY_RESPONSE",
        "news",
        "empty_response",
      ],
      [
        "https://stand.invalid/api/v1/stories?token=private-marker",
        "net::ERR_CONNECTION_RESET",
        "stories",
        "connection_reset",
      ],
      [
        "https://stand.invalid/api/v1/schedule/private-marker",
        "net::ERR_FAILED",
        "schedule",
        "failed",
      ],
      [
        "https://stand.invalid/api/v1/users/me",
        "net::ERR_NETWORK_CHANGED",
        "profile",
        "network_changed",
      ],
      [
        "https://stand.invalid/api/v1/notifications",
        "net::ERR_INTERNET_DISCONNECTED",
        "notifications",
        "internet_disconnected",
      ],
      [
        "https://third.invalid/api/v1/events?token=private-marker",
        "net::ERR_FAILED private-marker",
        "other",
        "other",
      ],
      [
        "https://stand.invalid/api/v1/events-private-marker",
        "private-marker net::ERR_EMPTY_RESPONSE",
        "other",
        "other",
      ],
    ]
    for (const [url, errorText] of cases) {
      const record = requestFailureRecord(visualFailure(url, errorText))
      assert.equal(record.errorText, errorText)
    }
    assert.equal(lines.length, cases.length)
    for (let index = 0; index < lines.length; index++) {
      assert.ok(lines[index].startsWith("visual-request-diagnostics "))
      const record = JSON.parse(lines[index].slice("visual-request-diagnostics ".length))
      assert.equal(record.apiFamily, cases[index][2])
      assert.equal(record.errorCode, cases[index][3])
      assert.equal(record.route, "/dashboard")
      assert.equal(record.width, 1440)
      assert.doesNotMatch(
        lines[index],
        /private-marker|stand\.invalid|third\.invalid|token=|\/api\/v1\//u
      )
    }
  })
})

test("visual request diagnostics are bounded, optional and cannot change failure records", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    const req = visualFailure("https://stand.invalid/api/v1/events", "net::ERR_FAILED")
    process.env.VISUAL_CAPTURE_MATRIX = "0"
    assert.equal(requestFailureRecord(req).errorText, "net::ERR_FAILED")
    assert.equal(lines.length, 0)
    process.env.VISUAL_CAPTURE_MATRIX = "1"
    for (let count = 0; count < 70; count++) requestFailureRecord(req)
    assert.equal(lines.length, 64)
  })
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }) => {
    console.log = () => {
      throw new Error("private-marker")
    }
    const req = visualFailure("https://stand.invalid/api/v1/events", "net::ERR_FAILED")
    assert.equal(requestFailureRecord(req).errorText, "net::ERR_FAILED")
  })
})

test("visual request diagnostics safely classify invalid inputs without exposing them", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    const req = visualFailure("not a url private-marker", "private-marker", "/other", 999)
    assert.equal(requestFailureRecord(req).errorText, "private-marker")
    assert.equal(lines.length, 1)
    const record = JSON.parse(lines[0].slice("visual-request-diagnostics ".length))
    assert.equal(record.apiFamily, "other")
    assert.equal(record.errorCode, "other")
    assert.equal(record.requestOrigin, "invalid")
    assert.equal(record.route, "other")
    assert.equal(record.width, 0)
    assert.doesNotMatch(lines[0], /private-marker|stand\.invalid/u)
  })
})

test("visual request diagnostics recognize the complete closed browser error inventory", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    const symbols = [
      ["ERR_FAILED", "failed"],
      ["ERR_EMPTY_RESPONSE", "empty_response"],
      ["ERR_HTTP2_PROTOCOL_ERROR", "http2_protocol_error"],
      ["ERR_HTTP2_SERVER_REFUSED_STREAM", "http2_server_refused_stream"],
      ["ERR_HTTP2_PING_FAILED", "http2_ping_failed"],
      ["ERR_CONTENT_LENGTH_MISMATCH", "content_length_mismatch"],
      ["ERR_INCOMPLETE_CHUNKED_ENCODING", "incomplete_chunked_encoding"],
      ["ERR_NETWORK_CHANGED", "network_changed"],
      ["ERR_INTERNET_DISCONNECTED", "internet_disconnected"],
      ["ERR_ADDRESS_UNREACHABLE", "address_unreachable"],
      ["ERR_CONNECTION_RESET", "connection_reset"],
      ["ERR_CONNECTION_CLOSED", "connection_closed"],
      ["ERR_CONNECTION_REFUSED", "connection_refused"],
      ["ERR_BLOCKED_BY_CLIENT", "blocked_by_client"],
      ["ERR_NAME_NOT_RESOLVED", "name_not_resolved"],
      ["ERR_TIMED_OUT", "timed_out"],
    ]
    for (const [symbol] of symbols) {
      requestFailureRecord(visualFailure("https://stand.invalid/api/v1/events", `net::${symbol}`))
    }
    assert.equal(lines.length, symbols.length)
    for (const [index, line] of lines.entries()) {
      assert.equal(
        JSON.parse(line.slice("visual-request-diagnostics ".length)).errorCode,
        symbols[index][1]
      )
    }
  })
})

test("visual request diagnostics fail closed for missing page data and inactive audit processes", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    const req = visualFailure("https://stand.invalid/api/v1/events/private-marker", "")
    req.method = () => "private-marker"
    req.frame = () => {
      throw new Error("private-marker")
    }
    assert.equal(requestFailureRecord(req).errorText, "")
    assert.equal(lines.length, 1)
    const record = JSON.parse(lines[0].slice("visual-request-diagnostics ".length))
    assert.equal(record.route, "other")
    assert.equal(record.width, 0)
    assert.equal(record.method, "other")
    assert.equal(record.apiFamily, "events")
    assert.equal(record.errorCode, "unknown")
    assert.doesNotMatch(lines[0], /private-marker|stand\.invalid/u)

    process.env.ORIGIN = "not a valid origin private-marker"
    assert.equal(requestFailureRecord(req).errorText, "")
    assert.equal(lines.length, 1)
    process.env.ORIGIN = "https://stand.invalid"
    process.argv[1] = "unrelated-script.mjs"
    assert.equal(requestFailureRecord(req).errorText, "")
    assert.equal(lines.length, 1)
  })
})

test("visual request diagnostics classify missing browser error text as unknown without changing records", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    for (const failure of [null, {}, { errorText: undefined }, { errorText: null }]) {
      const request = visualFailure("https://stand.invalid/api/v1/events", "unused")
      request.failure = () => failure
      assert.equal(requestFailureRecord(request).errorText, "unknown network failure")
    }
    const empty = visualFailure("https://stand.invalid/api/v1/events", "")
    assert.equal(requestFailureRecord(empty).errorText, "")
    assert.equal(lines.length, 5)
    for (const line of lines) {
      assert.equal(
        JSON.parse(line.slice("visual-request-diagnostics ".length)).errorCode,
        "unknown"
      )
    }
  })
})

test("visual request diagnostics exclude ordinary aborts from their cap without altering the records", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    for (let index = 0; index < 70; index++) {
      const request = visualFailure("https://stand.invalid/api/v1/events", "net::ERR_ABORTED")
      assert.equal(requestFailureRecord(request).errorText, "net::ERR_ABORTED")
    }
    assert.equal(lines.length, 0)
    requestFailureRecord(visualFailure("https://stand.invalid/api/v1/events", "net::ERR_FAILED"))
    assert.equal(lines.length, 1)
    assert.equal(
      JSON.parse(lines[0].slice("visual-request-diagnostics ".length)).errorCode,
      "failed"
    )
  })
})

test("visual request diagnostics distinguish fixed candidate API families and resource types", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    const cases = [
      [
        "https://stand.invalid/api/v1/campus/config?private=private-marker",
        "fetch",
        "campus",
        "fetch",
      ],
      ["https://stand.invalid/api/v1/img/media/private-marker", "image", "img", "image"],
      ["https://stand.invalid/api/v1/auth/session/signing-key", "xhr", "auth", "xhr"],
      ["https://stand.invalid/api/v1/push/topics", "fetch", "push", "fetch"],
      ["https://stand.invalid/api/v1/groups", "xhr", "groups", "xhr"],
      ["https://stand.invalid/api/v1/users/private-marker", "image", "users", "image"],
      ["https://stand.invalid/api/v1/campus-private-marker", "private-marker", "other", "other"],
      ["https://third.invalid/api/v1/campus/config", "fetch", "other", "fetch"],
    ]
    for (const [url, resourceType] of cases) {
      const request = visualFailure(url, "net::ERR_FAILED")
      request.resourceType = () => resourceType
      assert.equal(requestFailureRecord(request).errorText, "net::ERR_FAILED")
    }
    assert.equal(lines.length, cases.length)
    for (const [index, line] of lines.entries()) {
      const record = JSON.parse(line.slice("visual-request-diagnostics ".length))
      assert.equal(record.apiFamily, cases[index][2])
      assert.equal(record.resourceType, cases[index][3])
      assert.doesNotMatch(line, /private-marker|stand\.invalid|third\.invalid|\/api\/v1\//u)
    }
  })
})

test("visual request diagnostics bound missing or throwing resource types without changing the failure record", async () => {
  await withVisualRequestDiagnostics(async ({ requestFailureRecord }, lines) => {
    const request = visualFailure("https://stand.invalid/api/v1/campus/config", "net::ERR_FAILED")
    assert.equal(requestFailureRecord(request).errorText, "net::ERR_FAILED")
    request.resourceType = () => {
      throw new Error("private-marker")
    }
    assert.equal(requestFailureRecord(request).errorText, "net::ERR_FAILED")
    assert.equal(lines.length, 2)
    for (const line of lines) {
      assert.equal(
        JSON.parse(line.slice("visual-request-diagnostics ".length)).resourceType,
        "unknown"
      )
      assert.doesNotMatch(line, /private-marker|stand\.invalid/u)
    }
  })
})
