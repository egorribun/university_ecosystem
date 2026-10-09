import {
  expect,
  request,
  test as base,
  type APIRequestContext,
  type Browser,
  type Page,
  type Request,
  type Response,
  type TestInfo,
} from "@playwright/test"
import {
  createLivePageErrorDiagnostics,
  isLiveAdminNotificationsScenario,
  isLiveAuthRoleDenialScenario,
} from "./page-error-diagnostic"
import { requireLiveAdminPassword } from "../../scripts/live-e2e-credentials.mjs"
import { reportLiveHttpStatus, reportLiveRateLimitRetry } from "./http-status-diagnostic"

/**
 * Accounts created by scripts/seed_demo_data.py and scripts/seed_admin_data.py
 * inside the disposable live stand. They exist nowhere else.
 */
export const ROLES = {
  student: {
    email: "test@university.dev",
    password: "TestPass@2024x", // pragma: allowlist secret -- disposable stand seed account
  },
  teacher: {
    email: "olga.morozova@university.dev",
    password: "Teacher@2024test", // pragma: allowlist secret -- disposable stand seed account
  },
  admin: {
    email: "admin@university.dev",
    password: requireLiveAdminPassword(),
  },
} as const

export type Role = keyof typeof ROLES

/** Additional seeded accounts used only to form an isolated live group chat. */
export const GROUP_CHAT_ACCOUNTS = {
  secondMember: {
    email: "ivan.sokolov@university.dev",
    password: "Student@2024test", // pragma: allowlist secret -- disposable stand seed account
  },
  nonMember: {
    email: "sergey.lebedev@university.dev",
    password: "Teacher@2024test", // pragma: allowlist secret -- disposable stand seed account
  },
} as const

/** Stable name lets the live group isolation scenario safely reuse its own group. */
export const LIVE_GROUP_CHAT_NAME = "University Ecosystem live Messenger isolation"

const configuredMailpitURL = process.env.LIVE_MAILPIT_URL
if (!configuredMailpitURL) {
  throw new Error("LIVE_MAILPIT_URL must be set to the endpoint printed by scripts/live_stand.py")
}
const mailpitURL = new URL(configuredMailpitURL)
if (
  mailpitURL.protocol !== "http:" ||
  !["localhost", "127.0.0.1"].includes(mailpitURL.hostname) ||
  mailpitURL.username !== "" ||
  mailpitURL.password !== "" ||
  !mailpitURL.port ||
  Number(mailpitURL.port) < 20_000 ||
  Number(mailpitURL.port) > 45_000 ||
  mailpitURL.pathname !== "/" ||
  mailpitURL.search !== "" ||
  mailpitURL.hash !== ""
) {
  throw new Error("LIVE_MAILPIT_URL must use HTTP and an explicit live-stand loopback port")
}
const MAILPIT_URL = mailpitURL.toString().replace(/\/$/, "")

const LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS = 5_000
const LIVE_OWNED_CLEANUP_OPERATION_MARGIN_MS = 250

export function liveDeadlineBoundedTimeoutMs(
  deadlineAtMs: number,
  maximumMs: number,
  nowMs = performance.now()
): number | null {
  if (!Number.isFinite(deadlineAtMs) || !Number.isFinite(maximumMs) || maximumMs < 1) return null
  const remainingMs = Math.floor(deadlineAtMs - nowMs - LIVE_OWNED_CLEANUP_OPERATION_MARGIN_MS)
  return Number.isFinite(remainingMs) && remainingMs >= 1 ? Math.min(maximumMs, remainingMs) : null
}

function ownedCleanupOperationTimeout(deadlineAtMs: number, maximumMs: number): number {
  const timeoutMs = liveDeadlineBoundedTimeoutMs(deadlineAtMs, maximumMs)
  if (timeoutMs === null) throw new Error("Owned cleanup deadline exhausted")
  return timeoutMs
}

/** Submits the login form without asserting where it lands. */
export async function submitLogin(
  page: Page,
  email: string,
  password: string,
  cleanupDeadlineAtMs?: number,
  maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS
): Promise<void> {
  const operationOptions = (normalMaximumMs: number) =>
    cleanupDeadlineAtMs === undefined
      ? undefined
      : {
          timeout: ownedCleanupOperationTimeout(
            cleanupDeadlineAtMs,
            Math.min(normalMaximumMs, maximumOperationTimeoutMs)
          ),
        }
  await page.goto("/login", operationOptions(45_000))
  await page.getByRole("textbox", { name: "E-mail" }).fill(email, operationOptions(15_000))
  await page.getByLabel("Пароль", { exact: true }).fill(password, operationOptions(15_000))
  await page.getByRole("button", { name: "Войти" }).click(operationOptions(15_000))
}
type OwnedSessionCookie = {
  accessToken: string
  csrfToken: string | null
  cookieHeader: string
}

type OwnedLoginLease = {
  api: APIRequestContext
  sessions: OwnedSessionCookie[]
}

type OwnedSessionCleanupCallback = (browser: Browser, deadlineAtMs: number) => Promise<void>

type OwnedSessionScope = {
  leases: OwnedLoginLease[]
  issuedTokens: Set<string>
  captureFailed: boolean
  cleanupCallbacks: OwnedSessionCleanupCallback[]
}

const MAX_OWNED_SESSION_CLEANUP_CALLBACKS = 1
let activeOwnedSessionScope: OwnedSessionScope | undefined

export function registerOwnedSessionCleanup(callback: OwnedSessionCleanupCallback): void {
  const scope = activeOwnedSessionScope
  if (!scope) throw new Error("Owned resource cleanup requires the owned-session fixture")
  if (
    typeof callback !== "function" ||
    scope.cleanupCallbacks.length >= MAX_OWNED_SESSION_CLEANUP_CALLBACKS
  ) {
    throw new Error("Owned resource cleanup registration limit exceeded")
  }
  scope.cleanupCallbacks.push(callback)
}

type OwnedAuthStatusCheck =
  "auth-login" | "auth-session-cap" | "auth-logout" | "auth-session-preflight"

function reportOwnedAuthStatus(check: OwnedAuthStatusCheck, status: number): void {
  try {
    reportLiveHttpStatus(base.info().project.name, check, status)
  } catch {
    // Diagnostics must never replace the live test result.
  }
}

export function ownedSessionOrigin(): string {
  const configured = process.env.LIVE_BASE_URL
  if (!configured) throw new Error("LIVE_BASE_URL is required for owned session cleanup")

  let parsed: URL
  try {
    parsed = new URL(configured)
  } catch {
    throw new Error("LIVE_BASE_URL is invalid for owned session cleanup")
  }

  if (
    !["http:", "https:"].includes(parsed.protocol) ||
    !["localhost", "127.0.0.1"].includes(parsed.hostname) ||
    !parsed.port ||
    parsed.username ||
    parsed.password ||
    parsed.search ||
    parsed.hash ||
    (parsed.pathname !== "/" && parsed.pathname !== "")
  ) {
    throw new Error("LIVE_BASE_URL must be a loopback origin with an explicit port")
  }
  return parsed.origin
}

function ownedCookieHeader(
  accessToken: string,
  csrfCookies: Array<{ value: string }>,
  nonceCookies: Array<{ value: string }>
): { cookieHeader: string; csrfToken: string | null } {
  const csrfToken = csrfCookies.length === 1 ? (csrfCookies[0]?.value ?? null) : null
  const nonce = nonceCookies.length === 1 ? (nonceCookies[0]?.value ?? null) : null
  const values = [accessToken, csrfToken, nonce].filter(
    (value): value is string => typeof value === "string"
  )
  if (
    values.some((value) => value.length === 0 || /[;\r\n]/u.test(value)) ||
    csrfCookies.length !== 1 ||
    nonceCookies.length !== 1 ||
    !csrfToken ||
    !nonce
  ) {
    return { cookieHeader: "", csrfToken: null }
  }

  return {
    cookieHeader: [
      "access_token_v2=" + accessToken,
      "csrf_token=" + csrfToken,
      "_csrf_anon_nonce=" + nonce,
    ].join("; "),
    csrfToken,
  }
}

async function statusOnly(
  responsePromise: Promise<Awaited<ReturnType<APIRequestContext["get"]>>>
): Promise<number> {
  const response = await responsePromise
  try {
    return response.status()
  } finally {
    await response.dispose()
  }
}

const LIVE_SENSITIVE_WINDOW_SECONDS = 60
const LIVE_RETRY_MARGIN_MS = 250
const LIVE_MAX_RETRY_TEST_TIMEOUT_MS = 60_000
const LIVE_OWNED_SESSION_CLEANUP_TIMEOUT_MS = 60_000
const LIVE_OWNED_SESSION_SETUP_RESERVE_MS = 250
const LIVE_OWNED_SESSION_DISPOSE_RESERVE_MS = 500
const LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS = 5_000

export function parseLiveRateLimitRetryAfter(value: string | undefined): number | null {
  if (!value || !/^[1-9][0-9]*$/u.test(value)) return null
  const seconds = Number(value)
  return Number.isSafeInteger(seconds) && seconds <= LIVE_SENSITIVE_WINDOW_SECONDS ? seconds : null
}

export function liveRateLimitRetryFitsDeadline(
  deadlineAtMs: number,
  delaySeconds: number,
  requestBudgetMs: number,
  reserveMs = 0,
  nowMs = performance.now()
): boolean {
  if (!Number.isSafeInteger(delaySeconds) || delaySeconds < 0) return false
  if (!Number.isFinite(deadlineAtMs) || !Number.isFinite(nowMs)) return false
  if (!Number.isFinite(requestBudgetMs) || requestBudgetMs < 0) return false
  if (!Number.isFinite(reserveMs) || reserveMs < 0) return false
  const neededMs = delaySeconds * 1000 + requestBudgetMs + reserveMs + LIVE_RETRY_MARGIN_MS
  const remainingMs = deadlineAtMs - nowMs
  return Number.isFinite(remainingMs) && neededMs <= remainingMs
}

/**
 * Uses TestInfo's slot deadline from pinned @playwright/test 1.63.0. The API is
 * private and deliberately fails closed on an upgrade or an unexpected shape.
 */
export function liveTestSlotDeadlineAtMs(
  testInfo: TestInfo,
  nowMs = performance.now()
): number | null {
  if (!Number.isFinite(nowMs)) return null
  const timeoutMs = testInfo.timeout
  if (!Number.isFinite(timeoutMs) || timeoutMs <= 0 || timeoutMs > LIVE_MAX_RETRY_TEST_TIMEOUT_MS) {
    return null
  }
  let deadlineMethod: unknown
  try {
    deadlineMethod = Reflect.get(testInfo, "_deadline")
  } catch {
    return null
  }
  if (typeof deadlineMethod !== "function") return null

  let slot: unknown
  try {
    slot = Reflect.apply(deadlineMethod, testInfo, [])
  } catch {
    return null
  }
  if (typeof slot !== "object" || slot === null || Array.isArray(slot)) return null
  const values = slot as { deadline?: unknown; timeout?: unknown }
  if (
    typeof values.deadline !== "number" ||
    !Number.isFinite(values.deadline) ||
    values.timeout !== timeoutMs ||
    values.deadline <= nowMs ||
    values.deadline > nowMs + timeoutMs + 1
  ) {
    return null
  }
  return values.deadline
}

export type LiveRateLimitRetryDecision = "retry" | "declined-header" | "declined-deadline"

export function assessLiveRateLimitRetry(
  testInfo: TestInfo,
  delaySeconds: number | null,
  requestBudgetMs: number,
  reserveMs: number,
  nowMs = performance.now()
): { decision: LiveRateLimitRetryDecision; deadlineAtMs: number | null } {
  if (
    delaySeconds === null ||
    !Number.isSafeInteger(delaySeconds) ||
    delaySeconds < 0 ||
    delaySeconds > LIVE_SENSITIVE_WINDOW_SECONDS
  ) {
    return { decision: "declined-header", deadlineAtMs: null }
  }
  const deadlineAtMs = liveTestSlotDeadlineAtMs(testInfo, nowMs)
  if (
    deadlineAtMs === null ||
    !liveRateLimitRetryFitsDeadline(deadlineAtMs, delaySeconds, requestBudgetMs, reserveMs, nowMs)
  ) {
    return { decision: "declined-deadline", deadlineAtMs }
  }
  return { decision: "retry", deadlineAtMs }
}

export async function waitForLiveRateLimitRetry(delaySeconds: number): Promise<void> {
  await new Promise<void>((resolve) => {
    setTimeout(resolve, delaySeconds * 1000 + LIVE_RETRY_MARGIN_MS)
  })
}

async function statusAndRetryAfter(
  responsePromise: Promise<Awaited<ReturnType<APIRequestContext["get"]>>>
): Promise<{ status: number; retryAfter: string | undefined }> {
  const response = await responsePromise
  try {
    return { status: response.status(), retryAfter: response.headers()["retry-after"] }
  } finally {
    await response.dispose()
  }
}

async function runOwnedSessionCleanupCallbacks(
  scope: OwnedSessionScope,
  browser: Browser,
  deadlineAtMs: number
): Promise<string[]> {
  const failures: string[] = []
  const existingSessions = scope.leases.reduce((total, lease) => total + lease.sessions.length, 0)
  const plannedSessions = existingSessions + scope.cleanupCallbacks.length
  const plannedLeases = scope.leases.length + scope.cleanupCallbacks.length
  const leaseCleanupReserveMs =
    plannedSessions * 3 * LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS +
    plannedLeases * LIVE_OWNED_SESSION_DISPOSE_RESERVE_MS +
    LIVE_OWNED_SESSION_SETUP_RESERVE_MS
  const callbackDeadlineAtMs = deadlineAtMs - leaseCleanupReserveMs

  for (const callback of scope.cleanupCallbacks) {
    try {
      if (callbackDeadlineAtMs <= performance.now()) {
        throw new Error("Owned resource cleanup has no reserved time")
      }
      await callback(browser, callbackDeadlineAtMs)
    } catch {
      failures.push("owned-resource-cleanup")
    }
  }
  return failures
}

async function cleanupOwnedSessionScope(
  scope: OwnedSessionScope,
  deadlineAtMs: number,
  testInfo: TestInfo
): Promise<string[]> {
  const failures: string[] = []
  const totalSessions = scope.leases.reduce((total, lease) => total + lease.sessions.length, 0)
  let processedSessions = 0
  for (let leaseIndex = 0; leaseIndex < scope.leases.length; leaseIndex += 1) {
    const lease = scope.leases[leaseIndex]
    if (!lease) continue
    for (const session of lease.sessions) {
      processedSessions += 1
      try {
        const beforeLogout = await statusOnly(
          lease.api.get(new URL("/api/v1/users/me", ownedSessionOrigin()).toString(), {
            headers: {
              Authorization: "Bearer " + session.accessToken,
            },
            maxRedirects: 0,
            timeout: ownedCleanupOperationTimeout(
              deadlineAtMs,
              LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS
            ),
          })
        )
        if (beforeLogout === 401) continue
        if (beforeLogout !== 200) {
          reportOwnedAuthStatus("auth-session-preflight", beforeLogout)
          failures.push("session-preflight")
          continue
        }
        if (!session.csrfToken || !session.cookieHeader) {
          failures.push("csrf-cookie")
          continue
        }

        const csrfToken = session.csrfToken
        const cookieHeader = session.cookieHeader
        const logoutRequest = () =>
          lease.api.post(new URL("/api/v1/auth/logout", ownedSessionOrigin()).toString(), {
            headers: {
              Cookie: cookieHeader,
              "X-CSRF-Token": csrfToken,
            },
            maxRedirects: 0,
            timeout: ownedCleanupOperationTimeout(
              deadlineAtMs,
              LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS
            ),
          })
        const firstLogout = await statusAndRetryAfter(logoutRequest())
        let logoutStatus = firstLogout.status
        if (logoutStatus === 429) {
          reportOwnedAuthStatus("auth-logout", logoutStatus)
          const retryAfter = parseLiveRateLimitRetryAfter(firstLogout.retryAfter)
          const futureSessionCount = totalSessions - processedSessions
          const remainingRequestBudgetMs = 2 * 5000 + futureSessionCount * 3 * 5000
          const remainingDisposeReserveMs =
            (scope.leases.length - leaseIndex) * LIVE_OWNED_SESSION_DISPOSE_RESERVE_MS
          let retryDecision: "retry" | "declined-header" | "declined-deadline" =
            retryAfter === null ? "declined-header" : "declined-deadline"
          if (
            retryAfter !== null &&
            liveRateLimitRetryFitsDeadline(
              deadlineAtMs,
              retryAfter,
              remainingRequestBudgetMs,
              remainingDisposeReserveMs
            )
          ) {
            await waitForLiveRateLimitRetry(retryAfter)
            if (
              liveRateLimitRetryFitsDeadline(
                deadlineAtMs,
                0,
                remainingRequestBudgetMs,
                remainingDisposeReserveMs
              )
            ) {
              retryDecision = "retry"
              reportLiveRateLimitRetry(
                testInfo.project.name,
                "auth-logout",
                retryAfter,
                retryDecision,
                Math.max(0, Math.min(60_000, Math.floor(deadlineAtMs - performance.now())))
              )
              logoutStatus = await statusOnly(logoutRequest())
            } else {
              reportLiveRateLimitRetry(
                testInfo.project.name,
                "auth-logout",
                retryAfter,
                retryDecision,
                Math.max(0, Math.min(60_000, Math.floor(deadlineAtMs - performance.now())))
              )
            }
          } else {
            reportLiveRateLimitRetry(
              testInfo.project.name,
              "auth-logout",
              retryAfter,
              retryDecision,
              Math.max(0, Math.min(60_000, Math.floor(deadlineAtMs - performance.now())))
            )
          }
        }
        const afterLogout = await statusOnly(
          lease.api.get(new URL("/api/v1/users/me", ownedSessionOrigin()).toString(), {
            headers: {
              Authorization: "Bearer " + session.accessToken,
            },
            maxRedirects: 0,
            timeout: ownedCleanupOperationTimeout(
              deadlineAtMs,
              LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS
            ),
          })
        )
        if (logoutStatus !== 200) {
          reportOwnedAuthStatus("auth-logout", logoutStatus)
          failures.push("logout-status")
        }
        if (afterLogout !== 401) {
          reportOwnedAuthStatus("auth-logout", afterLogout)
          failures.push("revocation-status")
        }
      } catch {
        failures.push("request")
      }
    }

    try {
      await lease.api.dispose()
    } catch {
      failures.push("dispose")
    }
  }
  if (scope.captureFailed) failures.push("capture")
  return failures
}

async function isExactSessionCapResponse(response: Response): Promise<boolean> {
  try {
    if (response.status() !== 403) return false
    const contentLength = response.headers()["content-length"]
    if (!contentLength || !/^\d+$/u.test(contentLength) || Number(contentLength) > 16_384) {
      return false
    }
    const body: unknown = await response.json()
    return (
      typeof body === "object" &&
      body !== null &&
      "detail" in body &&
      body.detail === "too_many_sessions"
    )
  } catch {
    return false
  }
}

function isOwnedLoginRequest(candidate: Request, origin: string): boolean {
  try {
    const url = new URL(candidate.url())
    return (
      candidate.method() === "POST" &&
      url.origin === origin &&
      url.pathname === "/api/v1/auth/login"
    )
  } catch {
    return false
  }
}

async function createOwnedLoginLease(
  loginRequest: Request,
  origin: string,
  scope: OwnedSessionScope,
  cleanupDeadlineAtMs?: number
): Promise<OwnedLoginLease> {
  const userAgent = await loginRequest.headerValue("user-agent")
  const acceptLanguage = await loginRequest.headerValue("accept-language")
  if (
    !userAgent ||
    !acceptLanguage ||
    userAgent.length > 512 ||
    acceptLanguage.length > 256 ||
    /[\r\n]/u.test(userAgent) ||
    /[\r\n]/u.test(acceptLanguage)
  ) {
    throw new Error("invalid browser fingerprint headers")
  }

  const api = await request.newContext({
    baseURL: origin,
    extraHTTPHeaders: {
      "User-Agent": userAgent,
      "Accept-Language": acceptLanguage,
    },
    ignoreHTTPSErrors: true,
    timeout:
      cleanupDeadlineAtMs === undefined
        ? LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS
        : ownedCleanupOperationTimeout(cleanupDeadlineAtMs, LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS),
  })
  const lease: OwnedLoginLease = { api, sessions: [] }
  scope.leases.push(lease)
  return lease
}

async function captureOwnedLoginSession(
  page: Page,
  scope: OwnedSessionScope,
  origin: string,
  previousTokens: Set<string>,
  lease: OwnedLoginLease | undefined,
  cleanupDeadlineAtMs?: number
): Promise<boolean> {
  let cookies: Array<{ name: string; value: string }>
  try {
    cookies = await page.context().cookies(origin)
  } catch {
    scope.captureFailed = true
    return false
  }

  const newTokens = [
    ...new Set(
      cookies.filter((cookie) => cookie.name === "access_token_v2").map((cookie) => cookie.value)
    ),
  ].filter((token) => !previousTokens.has(token))
  if (newTokens.length !== 1 || !lease) {
    scope.captureFailed = true
    return false
  }

  const [token] = newTokens
  if (!token || scope.issuedTokens.has(token)) {
    scope.captureFailed = true
    return false
  }
  scope.issuedTokens.add(token)

  const cookie = ownedCookieHeader(
    token,
    cookies.filter((item) => item.name === "csrf_token"),
    cookies.filter((item) => item.name === "_csrf_anon_nonce")
  )
  lease.sessions.push({
    accessToken: token,
    csrfToken: cookie.csrfToken,
    cookieHeader: cookie.cookieHeader,
  })
  if (!cookie.cookieHeader || !cookie.csrfToken) {
    scope.captureFailed = true
    return false
  }

  try {
    const preflight = await statusOnly(
      lease.api.get(new URL("/api/v1/users/me", origin).toString(), {
        headers: { Authorization: "Bearer " + token },
        maxRedirects: 0,
        timeout:
          cleanupDeadlineAtMs === undefined
            ? LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS
            : ownedCleanupOperationTimeout(
                cleanupDeadlineAtMs,
                LIVE_OWNED_SESSION_REQUEST_TIMEOUT_MS
              ),
      })
    )
    if (preflight !== 200) {
      reportOwnedAuthStatus("auth-session-preflight", preflight)
      scope.captureFailed = true
    }
  } catch {
    scope.captureFailed = true
  }
  return true
}

export async function loginWith(
  page: Page,
  email: string,
  password: string,
  cleanupDeadlineAtMs?: number,
  maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS
): Promise<void> {
  const scope = activeOwnedSessionScope
  if (!scope) throw new Error("Live login requires the owned-session cleanup fixture")
  const origin = ownedSessionOrigin()
  const context = page.context()
  const beforeCookies = await context.cookies(origin)
  const previousTokens = new Set(
    beforeCookies
      .filter((cookie) => cookie.name === "access_token_v2")
      .map((cookie) => cookie.value)
  )

  let matchingRequests = 0
  let matchingResponses = 0
  let observedLoginRequest: Request | undefined
  let loginResponseStatus: number | undefined
  let loginDiagnosticPromise: Promise<void> | undefined
  let lease: OwnedLoginLease | undefined
  let leasePromise: Promise<void> | undefined
  let captureSetupFailed = false
  const observeRequest = (candidate: Request) => {
    if (!isOwnedLoginRequest(candidate, origin)) return
    matchingRequests += 1
    if (matchingRequests !== 1) {
      captureSetupFailed = true
      scope.captureFailed = true
      return
    }
    observedLoginRequest = candidate
    leasePromise = createOwnedLoginLease(candidate, origin, scope, cleanupDeadlineAtMs).then(
      (created) => {
        lease = created
      },
      () => {
        captureSetupFailed = true
        scope.captureFailed = true
      }
    )
  }
  const observeResponse = (candidate: Response) => {
    try {
      const responseRequest = candidate.request()
      if (!isOwnedLoginRequest(responseRequest, origin)) return
      matchingResponses += 1
      if (matchingRequests === 1 && matchingResponses === 1) {
        loginResponseStatus = candidate.status()
        if (loginResponseStatus !== 200) {
          loginDiagnosticPromise = (async () => {
            const check = (await isExactSessionCapResponse(candidate))
              ? "auth-session-cap"
              : "auth-login"
            reportOwnedAuthStatus(check, loginResponseStatus ?? 0)
          })()
        }
      }
    } catch {
      captureSetupFailed = true
      scope.captureFailed = true
    }
  }

  let primaryFailure: unknown
  let hasPrimaryFailure = false
  let captured = false
  try {
    try {
      context.on("request", observeRequest)
      context.on("response", observeResponse)
    } catch {
      captureSetupFailed = true
      scope.captureFailed = true
    }
    if (!captureSetupFailed) {
      try {
        await submitLogin(page, email, password, cleanupDeadlineAtMs, maximumOperationTimeoutMs)
        const dashboardExpectation =
          cleanupDeadlineAtMs === undefined
            ? expect
            : expect.configure({
                timeout: ownedCleanupOperationTimeout(
                  cleanupDeadlineAtMs,
                  Math.min(15_000, maximumOperationTimeoutMs)
                ),
              })
        await dashboardExpectation(page).toHaveURL(/\/dashboard$/)
      } catch (error) {
        primaryFailure = error
        hasPrimaryFailure = true
      }
    }
  } finally {
    try {
      context.off("request", observeRequest)
    } catch {
      captureSetupFailed = true
      scope.captureFailed = true
    }
    try {
      context.off("response", observeResponse)
    } catch {
      captureSetupFailed = true
      scope.captureFailed = true
    }
    if (leasePromise) await leasePromise
    if (loginDiagnosticPromise) await loginDiagnosticPromise
    if (
      matchingRequests !== 1 ||
      matchingResponses !== 1 ||
      loginResponseStatus !== 200 ||
      !observedLoginRequest
    ) {
      captureSetupFailed = true
      scope.captureFailed = true
    }
    try {
      captured = await captureOwnedLoginSession(
        page,
        scope,
        origin,
        previousTokens,
        lease,
        cleanupDeadlineAtMs
      )
    } catch {
      scope.captureFailed = true
    }
  }
  if (hasPrimaryFailure) throw primaryFailure
  if (!captured || captureSetupFailed) {
    throw new Error("Live login could not be safely registered for session cleanup")
  }
}

export async function loginAs(
  page: Page,
  role: Role,
  cleanupDeadlineAtMs?: number,
  maximumOperationTimeoutMs = LIVE_OWNED_CLEANUP_OPERATION_TIMEOUT_MS
): Promise<void> {
  await loginWith(
    page,
    ROLES[role].email,
    ROLES[role].password,
    cleanupDeadlineAtMs,
    maximumOperationTimeoutMs
  )
}

/**
 * A unique, strong password for accounts a spec creates itself. The browser's
 * breached-password lookup is stubbed per spec, so it never leaves the stand.
 */
export function freshPassword(): string {
  return `Live-${crypto.randomUUID().slice(0, 12)}-Pw9!`
}

export interface MailpitMessage {
  ID: string
  Subject: string
  To: { Address: string }[]
  Created: string
}

/** Newest-first messages addressed to `address` in the stand's Mailpit sink. */
export async function mailFor(address: string): Promise<MailpitMessage[]> {
  const response = await fetch(
    `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:${address}`)}`
  )
  expect(response.ok, `Mailpit search failed: ${response.status}`).toBe(true)
  const body = (await response.json()) as { messages: MailpitMessage[] }
  return body.messages
}

export async function mailText(id: string): Promise<string> {
  const response = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`)
  expect(response.ok, `Mailpit message ${id} failed: ${response.status}`).toBe(true)
  const body = (await response.json()) as { Text: string }
  return body.Text
}

/** Waits for the next message to `address` whose text matches `pattern`. */
export async function awaitMail(address: string, pattern: RegExp): Promise<RegExpMatchArray> {
  let match: RegExpMatchArray | null = null
  await expect
    .poll(
      async () => {
        for (const message of await mailFor(address)) {
          match = (await mailText(message.ID)).match(pattern)
          if (match) return true
        }
        return false
      },
      { message: `no mail to ${address} matching ${pattern}`, timeout: 30_000 }
    )
    .toBe(true)
  return match as unknown as RegExpMatchArray
}

/** Keeps the browser's HIBP range lookup inside the test: every password is unknown. */
export async function stubBreachedPasswordLookup(page: Page): Promise<void> {
  await page.route("https://api.pwnedpasswords.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/plain", body: "" })
  )
}

/** Fails the test on any uncaught page exception, the live lane's crash signal. */
export const test = base.extend<{
  pageErrors: Error[]
  ownedSessionCleanup: void
}>({
  ownedSessionCleanup: [
    // Playwright requires a destructured fixture argument even without dependencies.
    async ({ browser }, runTest, testInfo) => {
      const fixtureSetupStartedAt = performance.now()
      if (activeOwnedSessionScope) {
        throw new Error("Owned-session cleanup fixture scope overlapped")
      }
      const scope: OwnedSessionScope = {
        leases: [],
        issuedTokens: new Set<string>(),
        captureFailed: false,
        cleanupCallbacks: [],
      }
      activeOwnedSessionScope = scope
      const failures: string[] = []
      let primaryTestFailure: unknown
      let hasPrimaryTestFailure = false
      const fixtureSetupElapsedMs = performance.now() - fixtureSetupStartedAt
      try {
        await runTest()
      } catch (error) {
        primaryTestFailure = error
        hasPrimaryTestFailure = true
      } finally {
        const cleanupDeadlineAtMs =
          performance.now() +
          Math.max(
            0,
            LIVE_OWNED_SESSION_CLEANUP_TIMEOUT_MS -
              fixtureSetupElapsedMs -
              LIVE_OWNED_SESSION_SETUP_RESERVE_MS
          )
        try {
          failures.push(
            ...(await runOwnedSessionCleanupCallbacks(scope, browser, cleanupDeadlineAtMs))
          )
          failures.push(...(await cleanupOwnedSessionScope(scope, cleanupDeadlineAtMs, testInfo)))
        } catch {
          failures.push("cleanup")
        } finally {
          activeOwnedSessionScope = undefined
        }
      }
      if (failures.length > 0) {
        testInfo.annotations.push({
          type: "owned-session-cleanup",
          description: "One or more owned resources or sessions could not be cleaned and verified",
        })
        if (!hasPrimaryTestFailure && testInfo.errors.length === 0) {
          throw new Error("Owned live session cleanup could not be verified")
        }
      }
      if (hasPrimaryTestFailure) throw primaryTestFailure
    },
    { auto: true, timeout: LIVE_OWNED_SESSION_CLEANUP_TIMEOUT_MS },
  ],
  pageErrors: [
    async ({ page }, use, testInfo) => {
      const errors: Error[] = []
      const isResetScenario =
        (testInfo.project.name === "desktop" || testInfo.project.name === "mobile") &&
        testInfo.file.replace(/\\/g, "/").endsWith("/tests/e2e-live/password-reset.live.spec.ts") &&
        testInfo.title ===
          "a student resets with the Mailpit link without retaining tokens or following hostile redirects"
      const isAdminNotificationsScenario = isLiveAdminNotificationsScenario(
        testInfo.project.name,
        testInfo.file,
        testInfo.title
      )
      const isAuthRoleDenialScenario = isLiveAuthRoleDenialScenario(
        testInfo.project.name,
        testInfo.file,
        testInfo.title
      )
      const diagnosticCheck = isResetScenario
        ? "password-reset"
        : isAdminNotificationsScenario
          ? "admin-notifications"
          : isAuthRoleDenialScenario
            ? "auth-roles"
            : null
      const pageErrorDiagnostics = createLivePageErrorDiagnostics()
      page.on("pageerror", (error) => {
        errors.push(error)
        if (!diagnosticCheck) return
        let pathname = ""
        try {
          pathname = new URL(page.url()).pathname
        } catch {
          // An unavailable current URL is classified as other, never a new failure.
        }
        pageErrorDiagnostics.record(error, pathname, diagnosticCheck)
      })
      await use(errors)
      if (diagnosticCheck) pageErrorDiagnostics.report(testInfo.project.name, diagnosticCheck)
      expect(errors, errors.map((error) => error.message).join("\n")).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
