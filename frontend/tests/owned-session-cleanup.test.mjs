import { afterAll, beforeAll, beforeEach, expect, it, vi } from "vitest"
import { URL } from "node:url"

const state = vi.hoisted(() => ({
  definitions: undefined,
  scenario: {},
  apiContexts: [],
  apiOptions: [],
  project: "desktop",
  navigationAssertions: 0,
}))

vi.mock("../scripts/live-e2e-credentials.mjs", () => ({
  requireLiveAdminPassword: () => "synthetic-only-unused",
}))

vi.mock("@playwright/test", () => ({
  expect: () => ({
    async toHaveURL() {
      state.navigationAssertions += 1
      if (state.scenario.dashboardError) throw state.scenario.dashboardError
    },
  }),
  request: {
    async newContext(options) {
      state.apiOptions.push(options)
      const api = {
        getCalls: [],
        postCalls: [],
        getIndex: 0,
        disposed: 0,
        async get(url, requestOptions) {
          const statuses = state.scenario.getStatuses ?? [200, 200, 401]
          const status = statuses[this.getIndex++] ?? 500
          this.getCalls.push({ url, options: requestOptions, status })
          return { status: () => status, async dispose() {} }
        },
        async post(url, requestOptions) {
          this.postCalls.push({ url, options: requestOptions })
          const status = state.scenario.logoutStatus ?? 200
          return { status: () => status, async dispose() {} }
        },
        async dispose() {
          this.disposed += 1
        },
      }
      state.apiContexts.push(api)
      return api
    },
  },
  test: {
    info() {
      return { project: { name: state.project } }
    },
    extend(definitions) {
      state.definitions = definitions
      return {}
    },
  },
}))

let fixtureModule

beforeAll(async () => {
  vi.stubEnv("LIVE_BASE_URL", "http://127.0.0.1:38888")
  vi.stubEnv("LIVE_MAILPIT_URL", "http://127.0.0.1:38889")
  fixtureModule = await import("./e2e-live/fixtures.ts")
})

afterAll(() => {
  vi.unstubAllEnvs()
})

beforeEach(() => {
  state.scenario = {}
  state.apiContexts = []
  state.apiOptions = []
  state.project = "desktop"
  state.navigationAssertions = 0
})

function createPage(scenario = state.scenario) {
  const beforeCookies = [
    { name: "csrf_token", value: "synthetic-csrf" },
    { name: "_csrf_anon_nonce", value: "synthetic-nonce" },
    ...(scenario.beforeAccessToken
      ? [{ name: "access_token_v2", value: scenario.beforeAccessToken }]
      : []),
  ]
  const afterCookies = scenario.afterCookies ?? [
    { name: "csrf_token", value: "synthetic-csrf" },
    { name: "_csrf_anon_nonce", value: "synthetic-nonce" },
    { name: "access_token_v2", value: "synthetic-access-token" },
  ]
  const listeners = new Map()
  let cookieReads = 0
  const context = {
    closed: false,
    on(event, listener) {
      const current = listeners.get(event) ?? []
      current.push(listener)
      listeners.set(event, current)
    },
    off(event, listener) {
      listeners.set(
        event,
        (listeners.get(event) ?? []).filter((item) => item !== listener)
      )
    },
    async cookies() {
      if (this.closed) throw new Error("synthetic closed browser context")
      const cookies = cookieReads++ === 0 ? beforeCookies : afterCookies
      return cookies.map((cookie) => ({ ...cookie }))
    },
    async close() {
      this.closed = true
    },
    emit(event, value) {
      for (const listener of listeners.get(event) ?? []) listener(value)
    },
  }
  const loginRequest = {
    url: () => "http://127.0.0.1:38888/api/v1/auth/login",
    method: () => "POST",
    async headerValue(name) {
      if (name === "user-agent") return "synthetic-browser-ua"
      if (name === "accept-language") return "en-US,en;q=0.9"
      return null
    },
  }
  const loginResponse = {
    request: () => loginRequest,
    status: () => scenario.loginStatus ?? 200,
    headers: () => ({ "content-length": "32" }),
    async json() {
      return scenario.loginBody ?? { detail: "synthetic_failure" }
    },
  }
  const page = {
    context: () => context,
    async goto() {},
    getByRole() {
      return {
        async fill() {},
        async click() {
          context.emit("request", loginRequest)
          context.emit("response", loginResponse)
        },
      }
    },
    getByLabel() {
      return { async fill() {} }
    },
  }
  return { context, page }
}

function testInfo() {
  return { project: { name: state.project }, annotations: [], errors: [] }
}

async function runAutoCleanup(runTest, info = testInfo()) {
  const provider = state.definitions.ownedSessionCleanup[0]
  return await provider({}, runTest, info)
}

async function login(page) {
  await fixtureModule.loginWith(page, "synthetic-user", "synthetic-password")
}

it("logs out the exactly captured new token with the full CSRF tuple and verifies 401", async () => {
  state.scenario.beforeAccessToken = "synthetic-existing"
  const { page } = createPage()
  await runAutoCleanup(() => login(page))

  const api = state.apiContexts[0]
  const logout = api.postCalls[0]
  const paths = api.getCalls.map((call) => new URL(call.url).pathname)
  expect(Boolean(logout)).toBe(true)
  expect(logout.url.endsWith("/api/v1/auth/logout")).toBe(true)
  expect(logout.options.headers["X-CSRF-Token"] === "synthetic-csrf").toBe(true)
  expect(logout.options.headers.Cookie).toBe(
    "access_token_v2=synthetic-access-token; csrf_token=synthetic-csrf; _csrf_anon_nonce=synthetic-nonce"
  )
  expect(api.getCalls.map((call) => call.options.headers.Authorization)).toEqual([
    "Bearer synthetic-access-token",
    "Bearer synthetic-access-token",
    "Bearer synthetic-access-token",
  ])
  expect(api.getCalls.map((call) => call.status)).toEqual([200, 200, 401])
  expect(paths).toEqual(["/api/v1/users/me", "/api/v1/users/me", "/api/v1/users/me"])
  expect(api.disposed).toBe(1)
  expect(state.apiOptions[0].extraHTTPHeaders).toEqual({
    "User-Agent": "synthetic-browser-ua",
    "Accept-Language": "en-US,en;q=0.9",
  })
})

it("revokes through the independent API lease after the browser context closes", async () => {
  const { context, page } = createPage()
  await runAutoCleanup(async () => {
    await login(page)
    await context.close()
  })

  expect(context.closed).toBe(true)
  expect(state.apiContexts[0].postCalls.length).toBe(1)
  expect(state.apiContexts[0].disposed).toBe(1)
})

it("cleans a successful login even when the dashboard assertion fails", async () => {
  const primary = new Error("synthetic dashboard assertion")
  state.scenario.dashboardError = primary
  const { page } = createPage()

  await expect(runAutoCleanup(() => login(page))).rejects.toBe(primary)
  expect(state.apiContexts[0].postCalls.length).toBe(1)
  expect(state.apiContexts[0].disposed).toBe(1)
})

it.each([
  [
    "unchanged pre-existing token",
    (scenario) => {
      scenario.beforeAccessToken = "synthetic-existing"
      scenario.afterCookies = [
        { name: "csrf_token", value: "synthetic-csrf" },
        { name: "_csrf_anon_nonce", value: "synthetic-nonce" },
        { name: "access_token_v2", value: "synthetic-existing" },
      ]
    },
  ],
  [
    "ambiguous new tokens",
    (scenario) => {
      scenario.beforeAccessToken = "synthetic-existing"
      scenario.afterCookies = [
        { name: "csrf_token", value: "synthetic-csrf" },
        { name: "_csrf_anon_nonce", value: "synthetic-nonce" },
        { name: "access_token_v2", value: "synthetic-existing" },
        { name: "access_token_v2", value: "synthetic-new-one" },
        { name: "access_token_v2", value: "synthetic-new-two" },
      ]
    },
  ],
])("does not revoke an %s", async (_label, configure) => {
  configure(state.scenario)
  const { page } = createPage()
  await expect(runAutoCleanup(() => login(page))).rejects.toThrow(
    "Live login could not be safely registered"
  )
  expect(state.apiContexts[0].postCalls.length).toBe(0)
  expect(state.apiContexts[0].disposed).toBe(1)
})

it("fails closed after logout 429 and does not retry", async () => {
  state.scenario.logoutStatus = 429
  state.scenario.getStatuses = [200, 200, 200]
  const { page } = createPage()

  await expect(runAutoCleanup(() => login(page))).rejects.toThrow(
    "Owned live session cleanup could not be verified"
  )
  expect(state.apiContexts[0].postCalls.length).toBe(1)
  expect(state.apiContexts[0].getCalls.length).toBe(3)
  expect(state.apiContexts[0].disposed).toBe(1)
})

it("preserves the primary error despite logout failure and resets fixture scope", async () => {
  const primary = new Error("synthetic primary test error")
  state.scenario.dashboardError = primary
  state.scenario.logoutStatus = 429
  state.scenario.getStatuses = [200, 200, 200]
  const { page } = createPage()
  const info = testInfo()

  await expect(runAutoCleanup(() => login(page), info)).rejects.toBe(primary)
  expect(state.apiContexts[0].postCalls.length).toBe(1)
  expect(info.annotations).toEqual([
    {
      type: "owned-session-cleanup",
      description: "One or more owned sessions could not be revoked and verified",
    },
  ])

  state.scenario = {}
  await runAutoCleanup(async () => {})
})
