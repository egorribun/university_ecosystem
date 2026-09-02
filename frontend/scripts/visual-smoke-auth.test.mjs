import assert from "node:assert/strict"
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

test("authenticated and admin smoke scripts use browser-context login exclusively", async () => {
  for (const script of ["authenticated-visual-audit.mjs", "admin-visual-smoke.mjs"]) {
    const source = await readFile(new URL(script, import.meta.url), "utf8")
    assert.match(source, /loginBrowserContext/u)
    assert.doesNotMatch(source, /fetch\(`\$\{ORIGIN\}\/api\/v1\/auth\/login\/json/u)
    assert.doesNotMatch(source, /context\.addCookies/u)
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
