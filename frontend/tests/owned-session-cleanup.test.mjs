import { afterAll, beforeAll, beforeEach, expect, it, vi } from "vitest"
import { URL } from "node:url"
import packageJson from "../package.json" with { type: "json" }
import packageLock from "../package-lock.json" with { type: "json" }

const state = vi.hoisted(() => ({
  definitions: undefined,
  scenario: {},
  apiContexts: [],
  apiOptions: [],
  project: "desktop",
  navigationAssertions: 0,
  statusReports: [],
  retryReports: [],
  expectTimeouts: [],
  events: [],
  browserOptions: [],
  browserContexts: [],
  deletedUserIds: [],
  browser: undefined,
  pageContextCount: 0,
}))

vi.mock("../scripts/live-e2e-credentials.mjs", () => ({
  requireLiveAdminPassword: () => "synthetic-only-unused",
}))

vi.mock("./e2e-live/http-status-diagnostic", () => ({
  reportLiveHttpStatus(project, check, status) {
    state.statusReports.push([project, check, status])
  },
  reportLiveRateLimitRetry(project, check, retryAfter, decision, remainingMs) {
    state.retryReports.push([project, check, retryAfter, decision, remainingMs])
  },
}))

vi.mock("@playwright/test", () => {
  const expectMock = () => ({
    async toHaveURL() {
      state.navigationAssertions += 1
      if (state.scenario.dashboardError) throw state.scenario.dashboardError
    },
  })
  expectMock.configure = (options) => {
    state.expectTimeouts.push(options.timeout)
    return expectMock
  }
  return {
    expect: expectMock,
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
            state.events.push("session-logout")
            this.postCalls.push({ url, options: requestOptions })
            const statuses = state.scenario.logoutStatuses ?? [state.scenario.logoutStatus ?? 200]
            const status = statuses[this.postCalls.length - 1] ?? 500
            return {
              status: () => status,
              headers: () => ({ "retry-after": state.scenario.retryAfter }),
              async dispose() {},
            }
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
  }
})

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
  state.statusReports = []
  state.retryReports = []
  state.expectTimeouts = []
  state.events = []
  state.browserOptions = []
  state.browserContexts = []
  state.deletedUserIds = []
  state.browser = createBrowserMock()
  state.pageContextCount = 0
})

function createPage(scenario = state.scenario) {
  state.pageContextCount += 1
  const defaultAccessToken =
    state.pageContextCount === 1
      ? "synthetic-access-token"
      : `synthetic-access-token-${state.pageContextCount}`
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
    { name: "access_token_v2", value: scenario.accessToken ?? defaultAccessToken },
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
      state.events.push("browser-context-close")
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
    async evaluate(_callback, argument) {
      if (argument && typeof argument.userId === "string") {
        state.deletedUserIds.push(argument.userId)
        return scenario.deleteStatus ?? 200
      }
      throw new Error("unexpected synthetic page evaluation")
    },
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

function createBrowserMock() {
  return {
    async newContext(options) {
      state.browserOptions.push(options)
      const owned = createPage()
      owned.context.newPage = async () => owned.page
      state.browserContexts.push(owned.context)
      return owned.context
    },
  }
}

function testInfo({ timeout = 60_000 } = {}) {
  return { project: { name: state.project }, annotations: [], errors: [], timeout }
}

async function runAutoCleanup(runTest, info = testInfo()) {
  const provider = state.definitions.ownedSessionCleanup[0]
  return await provider({ browser: state.browser }, runTest, info)
}

async function login(page) {
  await fixtureModule.loginWith(page, "synthetic-user", "synthetic-password")
}

it("parses only positive integer Retry-After values through the sensitive window", () => {
  expect(fixtureModule.parseLiveRateLimitRetryAfter("1")).toBe(1)
  expect(fixtureModule.parseLiveRateLimitRetryAfter("60")).toBe(60)
  for (const value of [
    undefined,
    "",
    "0",
    "61",
    "01",
    "1.0",
    " 1",
    "1\n",
    "Wed, 21 Oct 2015 07:28:00 GMT",
  ]) {
    expect(fixtureModule.parseLiveRateLimitRetryAfter(value)).toBeNull()
  }
})

it("uses the real remaining budget instead of an arbitrary short delay ceiling", () => {
  expect(fixtureModule.liveRateLimitRetryFitsDeadline(60_000, 40, 10_000, 9_000, 0)).toBe(true)
  expect(fixtureModule.liveRateLimitRetryFitsDeadline(60_000, 41, 10_000, 9_000, 0)).toBe(false)
  expect(fixtureModule.liveRateLimitRetryFitsDeadline(60_000, 1, 10_000, 9_000, 45_001)).toBe(false)
})

it("uses the pinned test-slot deadline after setup elapsed and preserves a valid retry window", () => {
  const info = {
    ...testInfo(),
    _deadline: () => ({ deadline: 60_000, timeout: 60_000 }),
  }
  const slotDeadline = fixtureModule.liveTestSlotDeadlineAtMs(info, 10_000)
  expect(slotDeadline).toBe(60_000)
  expect(slotDeadline).not.toBe(70_000)

  const beforeBody = fixtureModule.assessLiveRateLimitRetry(info, 9, 20_000, 20_000, 10_000)
  expect(beforeBody).toEqual({ decision: "retry", deadlineAtMs: 60_000 })
  const afterRetryDelay = fixtureModule.assessLiveRateLimitRetry(info, 0, 20_000, 20_000, 19_250)
  expect(afterRetryDelay).toEqual({ decision: "retry", deadlineAtMs: 60_000 })
})

it.each([
  ["missing clock", testInfo()],
  [
    "thrown clock",
    {
      ...testInfo(),
      _deadline() {
        throw new Error("unavailable")
      },
    },
  ],
  ["malformed clock", { ...testInfo(), _deadline: () => ({ deadline: NaN, timeout: 60_000 }) }],
  [
    "mismatched timeout",
    { ...testInfo(), _deadline: () => ({ deadline: 60_000, timeout: 59_999 }) },
  ],
  ["expired slot", { ...testInfo(), _deadline: () => ({ deadline: 10_000, timeout: 60_000 }) }],
])("declines retry when the actual slot deadline is %s", (_label, info) => {
  expect(fixtureModule.liveTestSlotDeadlineAtMs(info, 20_000)).toBeNull()
  expect(fixtureModule.assessLiveRateLimitRetry(info, 1, 20_000, 20_000, 20_000)).toEqual({
    decision: "declined-deadline",
    deadlineAtMs: null,
  })
})

it("declines when reading the private slot clock throws", () => {
  const info = testInfo()
  Object.defineProperty(info, "_deadline", {
    get() {
      throw new Error("unavailable")
    },
  })
  expect(fixtureModule.liveTestSlotDeadlineAtMs(info, 20_000)).toBeNull()
  expect(fixtureModule.assessLiveRateLimitRetry(info, 1, 20_000, 20_000, 20_000)).toEqual({
    decision: "declined-deadline",
    deadlineAtMs: null,
  })
})

it("declines once delay, request and shared assertion tail no longer fit", () => {
  const info = {
    ...testInfo(),
    _deadline: () => ({ deadline: 60_000, timeout: 60_000 }),
  }
  expect(fixtureModule.assessLiveRateLimitRetry(info, 1, 20_000, 20_000, 19_800)).toEqual({
    decision: "declined-deadline",
    deadlineAtMs: 60_000,
  })
  expect(fixtureModule.liveDeadlineBoundedTimeoutMs(60_000, 15_000, 59_800)).toBeNull()
})

it("pins the private slot-deadline adapter to Playwright 1.63.0", () => {
  expect(packageJson.devDependencies["@playwright/test"]).toBe("1.63.0")
  expect(packageLock.packages["node_modules/@playwright/test"].version).toBe("1.63.0")
  expect(packageLock.packages["node_modules/playwright"].version).toBe("1.63.0")
  expect(packageLock.packages["node_modules/playwright-core"].version).toBe("1.63.0")
})

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

it("retries one logout only after the bounded Retry-After and verifies revocation", async () => {
  vi.useFakeTimers()
  try {
    state.scenario.logoutStatuses = [429, 200]
    state.scenario.retryAfter = "1"
    const { page } = createPage()
    const cleanup = runAutoCleanup(() => login(page))
    await vi.runAllTimersAsync()
    await cleanup

    const api = state.apiContexts[0]
    expect(api.postCalls.length).toBe(2)
    expect(api.postCalls[0].options).toEqual(api.postCalls[1].options)
    expect(api.getCalls.map((call) => call.status)).toEqual([200, 200, 401])
    expect(state.statusReports).toContainEqual(["desktop", "auth-logout", 429])
    expect(state.retryReports).toHaveLength(1)
    expect(state.retryReports[0]?.slice(0, 4)).toEqual(["desktop", "auth-logout", 1, "retry"])
    expect(state.retryReports[0]?.[4]).toBeGreaterThan(0)
    expect(api.disposed).toBe(1)
  } finally {
    vi.useRealTimers()
  }
})

it("fails closed when a valid logout Retry-After cannot fit remaining proof budget", async () => {
  state.scenario.logoutStatus = 429
  state.scenario.retryAfter = "60"
  state.scenario.getStatuses = [200, 200, 200]
  const { page } = createPage()

  await expect(runAutoCleanup(() => login(page))).rejects.toThrow(
    "Owned live session cleanup could not be verified"
  )
  expect(state.apiContexts[0].postCalls.length).toBe(1)
  expect(state.statusReports).toContainEqual(["desktop", "auth-logout", 429])
  expect(state.retryReports).toHaveLength(1)
  expect(state.retryReports[0]?.slice(0, 4)).toEqual([
    "desktop",
    "auth-logout",
    60,
    "declined-deadline",
  ])
  expect(state.retryReports[0]?.[4]).toBeGreaterThanOrEqual(0)
  expect(state.apiContexts[0].getCalls.map((call) => call.status)).toEqual([200, 200, 200])
  expect(state.apiContexts[0].disposed).toBe(1)
})

it("does not retry malformed logout Retry-After and reports a bounded decline", async () => {
  state.scenario.logoutStatus = 429
  state.scenario.retryAfter = "1.5"
  state.scenario.getStatuses = [200, 200, 200]
  const { page } = createPage()

  await expect(runAutoCleanup(() => login(page))).rejects.toThrow(
    "Owned live session cleanup could not be verified"
  )
  expect(state.apiContexts[0].postCalls.length).toBe(1)
  expect(state.retryReports).toHaveLength(1)
  expect(state.retryReports[0]?.slice(0, 4)).toEqual([
    "desktop",
    "auth-logout",
    null,
    "declined-header",
  ])
})

it("runs exact owned-resource cleanup before revoking callback-created sessions", async () => {
  const { page } = createPage()
  let deletedId = ""
  await runAutoCleanup(async () => {
    await login(page)
    fixtureModule.registerOwnedSessionCleanup(async (browser, deadlineAtMs) => {
      state.events.push("resource-cleanup-start")
      const context = await browser.newContext({ baseURL: "http://127.0.0.1:38888" })
      try {
        const cleanupPage = await context.newPage()
        await fixtureModule.loginAs(cleanupPage, "admin", deadlineAtMs, 5_000)
        await cleanupPage.evaluate(async () => 200, {
          userId: "synthetic-owned-user",
          timeoutMs: 1000,
        })
        deletedId = state.deletedUserIds.at(-1) ?? ""
      } finally {
        await context.close()
      }
      state.events.push("resource-cleanup-finished")
    })
  })

  expect(deletedId).toBe("synthetic-owned-user")
  expect(state.browserOptions).toEqual([{ baseURL: "http://127.0.0.1:38888" }])
  expect(state.events.indexOf("resource-cleanup-finished")).toBeLessThan(
    state.events.indexOf("session-logout")
  )
  expect(state.apiContexts).toHaveLength(2)
  expect(state.apiContexts.every((api) => api.postCalls.length === 1 && api.disposed === 1)).toBe(
    true
  )
  expect(state.browserContexts.every((context) => context.closed)).toBe(true)
})

it("fails cleanup on a non-200 exact-resource delete and still revokes its session", async () => {
  state.scenario.deleteStatus = 204
  await expect(
    runAutoCleanup(async () => {
      fixtureModule.registerOwnedSessionCleanup(async (browser, deadlineAtMs) => {
        const context = await browser.newContext({ baseURL: "http://127.0.0.1:38888" })
        try {
          const page = await context.newPage()
          await fixtureModule.loginAs(page, "admin", deadlineAtMs, 5_000)
          const status = await page.evaluate(async () => 200, {
            userId: "synthetic-owned-user",
            timeoutMs: 1_000,
          })
          if (status !== 200) throw new Error("Synthetic account cleanup did not return 200")
        } finally {
          await context.close()
        }
      })
    })
  ).rejects.toThrow("Owned live session cleanup could not be verified")
  expect(state.deletedUserIds).toEqual(["synthetic-owned-user"])
  expect(state.browserContexts.every((context) => context.closed)).toBe(true)
  expect(state.apiContexts).toHaveLength(1)
  expect(state.apiContexts[0].postCalls).toHaveLength(1)
  expect(state.apiContexts[0].disposed).toBe(1)
})

it("preserves the test error while callback failure is reported and session revocation continues", async () => {
  const primary = new Error("synthetic primary failure")
  const { page } = createPage()
  const info = testInfo()
  await expect(
    runAutoCleanup(async () => {
      await login(page)
      fixtureModule.registerOwnedSessionCleanup(async (browser, deadlineAtMs) => {
        const context = await browser.newContext({ baseURL: "http://127.0.0.1:38888" })
        try {
          await fixtureModule.loginAs(await context.newPage(), "admin", deadlineAtMs, 5_000)
          throw new Error("synthetic owned-resource cleanup failure")
        } finally {
          await context.close()
        }
      })
      throw primary
    }, info)
  ).rejects.toBe(primary)
  expect(state.apiContexts).toHaveLength(2)
  expect(state.apiContexts.every((api) => api.postCalls.length === 1 && api.disposed === 1)).toBe(
    true
  )
  expect(state.browserContexts.every((context) => context.closed)).toBe(true)
  expect(info.annotations).toEqual([
    {
      type: "owned-session-cleanup",
      description: "One or more owned resources or sessions could not be cleaned and verified",
    },
  ])
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
      description: "One or more owned resources or sessions could not be cleaned and verified",
    },
  ])

  state.scenario = {}
  await runAutoCleanup(async () => {})
})
