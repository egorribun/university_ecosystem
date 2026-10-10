import { randomUUID } from "node:crypto"
import type { Page, Response } from "@playwright/test"
import {
  awaitMail,
  expect,
  freshPassword,
  loginAs,
  loginWith,
  assessLiveRateLimitRetry,
  liveDeadlineBoundedTimeoutMs,
  ownedSessionOrigin,
  parseLiveRateLimitRetryAfter,
  registerOwnedSessionCleanup,
  stubBreachedPasswordLookup,
  waitForLiveRateLimitRetry,
  submitLogin,
  test,
} from "./fixtures"

import { reportLiveHttpStatus, reportLiveRateLimitRetry } from "./http-status-diagnostic"

const RESET_LINK = /\/reset-password\?token=([\w.~-]+)/
const UNTRUSTED_REDIRECT = "https://redirect-target.invalid/landing"
const RESET_REPLAY_REQUEST_BUDGET_MS = 20_000
const RESET_REPLAY_TAIL_BUDGET_MS = 20_000
const RESET_REPLAY_ACTION_TIMEOUT_MS = 15_000

function boundedReplayTimeout(deadlineAtMs: number, maximumMs: number): number {
  const timeoutMs = liveDeadlineBoundedTimeoutMs(deadlineAtMs, maximumMs)
  if (timeoutMs === null) throw new Error("Password reset replay deadline exhausted")
  return timeoutMs
}

function expectWithinReplayDeadline(deadlineAtMs: number) {
  return expect.configure({
    timeout: boundedReplayTimeout(deadlineAtMs, RESET_REPLAY_ACTION_TIMEOUT_MS),
  })
}

async function withinReplayTail<T>(deadlineAtMs: number, action: () => Promise<T>): Promise<T> {
  const timeoutMs = boundedReplayTimeout(deadlineAtMs, RESET_REPLAY_TAIL_BUDGET_MS)
  let timer: ReturnType<typeof setTimeout> | undefined
  const deadlineFailure = new Promise<never>((_, reject) => {
    timer = setTimeout(
      () => reject(new Error("Password reset replay assertion deadline exhausted")),
      timeoutMs
    )
  })
  try {
    return await Promise.race([action(), deadlineFailure])
  } finally {
    if (timer !== undefined) clearTimeout(timer)
  }
}

const openResetLink = async (page: Page, url: string) => {
  try {
    await page.goto(url)
  } catch {
    throw new Error("Could not open the Mailpit reset link")
  }
}

const expectResetTokenRemovedFromUrl = async (page: Page, token: string) => {
  await expect
    .poll(() =>
      page.evaluate((candidate) => {
        const current = new URL(window.location.href)
        return (
          current.pathname === "/reset-password" &&
          !current.searchParams.has("token") &&
          !window.location.href.includes(candidate)
        )
      }, token)
    )
    .toBe(true)
}

test("a student resets with the Mailpit link without retaining tokens or following hostile redirects", async ({
  page,
}, testInfo) => {
  await stubBreachedPasswordLookup(page)
  const email = `live-reset-${testInfo.project.name}-${randomUUID()}@university.dev`
  const firstPassword = freshPassword()
  const newPassword = freshPassword()

  const registrationResponse = page.waitForResponse(
    (response) =>
      response.request().method() === "POST" &&
      new URL(response.url()).pathname.endsWith("/auth/register")
  )
  await page.goto("/register")
  await page.getByLabel("Имя", { exact: true }).fill("Live Acceptance")
  await page.getByRole("textbox", { name: "E-mail" }).fill(email)
  await page.getByLabel("Пароль", { exact: true }).fill(firstPassword)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(firstPassword)
  await page.getByRole("button", { name: "Зарегистрироваться" }).click()
  const registered = await registrationResponse
  expect(registered.ok()).toBe(true)
  const registrationBody = (await registered.json()) as { id?: unknown }
  if (typeof registrationBody.id !== "string" || registrationBody.id.length === 0) {
    throw new Error("Synthetic account registration returned no account id")
  }
  const createdUserId = registrationBody.id
  registerOwnedSessionCleanup(async (cleanupBrowser, cleanupDeadlineAtMs) => {
    const cleanupContext = await cleanupBrowser.newContext({
      baseURL: ownedSessionOrigin(),
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    try {
      const cleanupPage = await cleanupContext.newPage()
      await loginAs(cleanupPage, "admin", cleanupDeadlineAtMs, 5_000)
      const deleteTimeoutMs = boundedReplayTimeout(cleanupDeadlineAtMs, 5_000)
      const deleteStatus = await cleanupPage.evaluate(
        async ({ userId, timeoutMs }) => {
          const csrfCookie = document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith("csrf_token="))
          if (!csrfCookie) return 0

          const controller = new AbortController()
          const timer = window.setTimeout(() => controller.abort(), timeoutMs)
          try {
            const response = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
              method: "DELETE",
              credentials: "same-origin",
              redirect: "error",
              signal: controller.signal,
              headers: {
                Accept: "application/json",
                "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
                "X-Requested-With": "XMLHttpRequest",
              },
            })
            return response.status
          } finally {
            window.clearTimeout(timer)
          }
        },
        { userId: createdUserId, timeoutMs: deleteTimeoutMs }
      )
      if (deleteStatus !== 200) throw new Error("Synthetic account cleanup did not return 200")
    } finally {
      await cleanupContext.close()
    }
  })

  await expect(page).toHaveURL(/\/login/)
  await loginWith(page, email, firstPassword)
  await page.context().clearCookies()

  await page.goto("/forgot-password")
  await page.getByRole("textbox", { name: "E-mail" }).fill(email)
  await page.getByRole("button", { name: "Отправить ссылку" }).click()
  await expect(page.getByText("Проверьте почту")).toBeVisible()

  const resetMatch = await awaitMail(email, RESET_LINK)
  const token = resetMatch[1]
  if (!token) throw new Error("Mailpit reset message had no token")
  const resetUrl = new URL(resetMatch[0], page.url())
  resetUrl.searchParams.set("redirect", UNTRUSTED_REDIRECT)
  await openResetLink(page, resetUrl.href)
  await expectResetTokenRemovedFromUrl(page, token)
  await page.getByLabel("Пароль", { exact: true }).fill(newPassword)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(newPassword)
  await page.getByRole("button", { name: "Сохранить пароль" }).click()
  await expect(page.getByText("Пароль обновлён")).toBeVisible()

  const resetOrigin = new URL(page.url()).origin
  await page.getByRole("link", { name: "Перейти ко входу" }).click()
  await expect(page).toHaveURL(new URL("/login", resetOrigin).href)
  expect(new URL(page.url()).origin === resetOrigin).toBe(true)
  expect(new URL(page.url()).search === "").toBe(true)

  await page.goBack()
  await expectResetTokenRemovedFromUrl(page, token)
  const historyKeptResetRoute = await page.evaluate((target) => {
    const current = new URL(window.location.href)
    return current.pathname === "/reset-password" && current.searchParams.get("redirect") === target
  }, UNTRUSTED_REDIRECT)
  expect(historyKeptResetRoute).toBe(true)
  await page.goForward()
  await expect(page).toHaveURL(new URL("/login", resetOrigin).href)

  await submitLogin(page, email, firstPassword)
  const rejectedLoginAlert = page
    .locator("form")
    .filter({ has: page.locator("#login-submit") })
    .getByRole("alert")
  await expect(rejectedLoginAlert).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
  await loginWith(page, email, newPassword)
  await page.context().clearCookies()

  // The link is single-use: a second reset with the same token is refused.
  const replayUrl = new URL("/reset-password", page.url())
  replayUrl.searchParams.set("token", token)
  await openResetLink(page, replayUrl.href)
  await expectResetTokenRemovedFromUrl(page, token)
  const replayPassword = freshPassword()
  await page.getByLabel("Пароль", { exact: true }).fill(replayPassword)
  await page.getByLabel("Повторите пароль", { exact: true }).fill(replayPassword)
  const isPasswordResetResponse = (response: Response) =>
    response.request().method() === "POST" &&
    new URL(response.url()).pathname.endsWith("/password/reset")
  const replayResponse = page.waitForResponse(isPasswordResetResponse)
  await page.getByRole("button", { name: "Сохранить пароль" }).click()
  const firstReplayResult = await replayResponse
  const firstReplayStatus = firstReplayResult.status()
  reportLiveHttpStatus(testInfo.project.name, "password-reset-replay", firstReplayStatus)
  let replayStatus = firstReplayStatus
  let retryTailDeadlineAtMs: number | null = null
  if (firstReplayStatus === 429) {
    const retryAfter = parseLiveRateLimitRetryAfter(firstReplayResult.headers()["retry-after"])
    const initialDecision = assessLiveRateLimitRetry(
      testInfo,
      retryAfter,
      RESET_REPLAY_REQUEST_BUDGET_MS,
      RESET_REPLAY_TAIL_BUDGET_MS
    )
    let retryDecision = initialDecision.decision
    let retryDeadlineAtMs = initialDecision.deadlineAtMs

    if (initialDecision.decision === "retry" && retryAfter !== null) {
      await waitForLiveRateLimitRetry(retryAfter)
      const afterWait = assessLiveRateLimitRetry(
        testInfo,
        0,
        RESET_REPLAY_REQUEST_BUDGET_MS,
        RESET_REPLAY_TAIL_BUDGET_MS
      )
      retryDecision = afterWait.decision
      retryDeadlineAtMs = afterWait.deadlineAtMs

      if (afterWait.decision === "retry" && afterWait.deadlineAtMs !== null) {
        const requestDeadlineAtMs = afterWait.deadlineAtMs - RESET_REPLAY_TAIL_BUDGET_MS
        const responseTimeoutMs = liveDeadlineBoundedTimeoutMs(requestDeadlineAtMs, 5_000)
        const clickTimeoutMs = liveDeadlineBoundedTimeoutMs(
          requestDeadlineAtMs,
          RESET_REPLAY_ACTION_TIMEOUT_MS
        )
        if (responseTimeoutMs !== null && clickTimeoutMs !== null) {
          retryDecision = "retry"
          reportLiveRateLimitRetry(
            testInfo.project.name,
            "password-reset-replay",
            retryAfter,
            retryDecision,
            Math.max(0, Math.floor(afterWait.deadlineAtMs - performance.now()))
          )
          const retryResponse = page.waitForResponse(isPasswordResetResponse, {
            timeout: responseTimeoutMs,
          })
          const retryClick = page
            .getByRole("button", { name: "Сохранить пароль" })
            .click({ timeout: clickTimeoutMs })
          const [responseOutcome, clickOutcome] = await Promise.allSettled([
            retryResponse,
            retryClick,
          ])
          if (responseOutcome.status === "rejected") throw responseOutcome.reason
          if (clickOutcome.status === "rejected") throw clickOutcome.reason
          replayStatus = responseOutcome.value.status()
          reportLiveHttpStatus(testInfo.project.name, "password-reset-replay", replayStatus)
          retryTailDeadlineAtMs = Math.min(
            afterWait.deadlineAtMs,
            performance.now() + RESET_REPLAY_TAIL_BUDGET_MS
          )
        } else {
          retryDecision = "declined-deadline"
        }
      }
    }

    if (retryDecision !== "retry") {
      reportLiveRateLimitRetry(
        testInfo.project.name,
        "password-reset-replay",
        retryAfter,
        retryDecision,
        retryDeadlineAtMs === null
          ? 0
          : Math.max(0, Math.floor(retryDeadlineAtMs - performance.now()))
      )
    }
  }
  expect(replayStatus, "a consumed reset token must be rejected by the API").toBe(400)
  // Scope to the reset form so the app's empty global live region cannot
  // satisfy this assertion before the consumed-token error is rendered.
  const assertReplayFeedback = async (deadlineAtMs?: number) => {
    const replayExpect =
      deadlineAtMs === undefined ? expect : expectWithinReplayDeadline(deadlineAtMs)
    const replayAlert = page
      .locator("form")
      .filter({ has: page.locator("#reset-submit-btn") })
      .getByRole("alert")
    await replayExpect(replayAlert).toBeVisible()
    const replayFeedback = await replayAlert.evaluate(
      (alert, resetToken) => ({
        isNonEmpty: Boolean(alert.textContent?.trim()),
        containsResetToken: alert.textContent?.includes(resetToken) ?? false,
      }),
      token
    )
    expect(replayFeedback.isNonEmpty).toBe(true)
    expect(replayFeedback.containsResetToken).toBe(false)
    const hiddenExpectation =
      deadlineAtMs === undefined ? expect : expectWithinReplayDeadline(deadlineAtMs)
    await hiddenExpectation(
      page.getByText(
        "\u041f\u0430\u0440\u043e\u043b\u044c \u043e\u0431\u043d\u043e\u0432\u043b\u0451\u043d"
      )
    ).toBeHidden()
    await submitLogin(page, email, replayPassword, deadlineAtMs, 45_000)
    const loginExpectation =
      deadlineAtMs === undefined ? expect : expectWithinReplayDeadline(deadlineAtMs)
    await loginExpectation(page).toHaveURL(/\/login/)
  }

  if (retryTailDeadlineAtMs === null) {
    await assertReplayFeedback()
  } else {
    await withinReplayTail(retryTailDeadlineAtMs, () => assertReplayFeedback(retryTailDeadlineAtMs))
  }
})
