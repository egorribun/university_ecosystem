import { randomUUID } from "node:crypto"
import { expect, freshPassword, loginAs, loginWith, submitLogin, test } from "./fixtures"
import type { Page } from "@playwright/test"

const LOCKOUT_ATTEMPTS = 5

async function deleteOwnedAccount(adminPage: Page, userId: string): Promise<void> {
  const cleanup = await adminPage.evaluate(async (accountId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, deleted: false }

    const response = await fetch(`/api/v1/users/${encodeURIComponent(accountId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: {
        Accept: "application/json",
        "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
        "X-Requested-With": "XMLHttpRequest",
      },
    })
    const body = (await response.json().catch(() => null)) as { deleted?: boolean } | null
    return { status: response.status, deleted: body?.deleted === true }
  }, userId)
  expect(cleanup.status, "cleanup targets the exact synthetic account created by this test").toBe(
    200
  )
  expect(cleanup.deleted).toBe(true)
}

test("synthetic account reaches account lockout after the configured failed-login threshold", async ({
  browser,
  page,
}) => {
  test.setTimeout(90_000)
  const email = `live-auth-lockout-${randomUUID()}@university.dev`
  const fullName = `Live Auth Lockout ${randomUUID()}`
  const password = freshPassword()
  const wrongPassword = freshPassword()
  const adminContext = await browser.newContext({
    baseURL: process.env.LIVE_BASE_URL,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminPage = await adminContext.newPage()
  let createdUserId: string | null = null

  try {
    await loginAs(adminPage, "admin")
    const creation = await adminPage.evaluate(
      async (user) => {
        const csrfCookie = document.cookie
          .split(";")
          .map((part) => part.trim())
          .find((part) => part.startsWith("csrf_token="))
        if (!csrfCookie) return { status: 0, id: null }

        const response = await fetch("/api/v1/users", {
          method: "POST",
          credentials: "same-origin",
          headers: {
            Accept: "application/json",
            "Content-Type": "application/json",
            "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
            "X-Requested-With": "XMLHttpRequest",
          },
          body: JSON.stringify(user),
        })
        const body = (await response.json().catch(() => null)) as { id?: unknown } | null
        return {
          status: response.status,
          id: body && typeof body.id === "string" ? body.id : null,
        }
      },
      { email, full_name: fullName, password, role: "student" }
    )
    if (creation.id) createdUserId = creation.id
    expect(creation.status, "admin creates a synthetic account owned by this test").toBe(200)
    if (!createdUserId) throw new Error("Synthetic login account creation returned no account id")

    const uiFailureResponsePromise = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/auth/login")
    )
    await submitLogin(page, email, wrongPassword)
    const uiFailureResponse = await uiFailureResponsePromise
    expect(uiFailureResponse.status(), "the real login form rejects wrong credentials").toBe(401)
    await expect(page).toHaveURL(/\/login$/u)
    const visibleLoginError = page.locator("form").getByRole("alert").filter({ hasText: /\S/u })
    await expect(visibleLoginError).toBeVisible()

    await loginWith(page, email, password)
    const identityResponse = await page.request.get("/api/v1/users/me")
    expect(identityResponse.status(), "the synthetic account owns this browser session").toBe(200)
    expect((await identityResponse.json()).id).toBe(createdUserId)

    const sessionCookies = await page.context().cookies()
    expect(
      sessionCookies.some((cookie) => cookie.name === "access_token_v2"),
      "the synthetic account's authenticated cookie keeps subsequent login attempts in its own rate-limit bucket"
    ).toBe(true)

    // The successful login clears the UI failure above. BrowserContext.request
    // shares this synthetic user's cookie, so these failed attempts use that
    // user's isolated rate-limit bucket instead of consuming the shared IP key.
    for (let attempt = 1; attempt <= LOCKOUT_ATTEMPTS; attempt += 1) {
      const response = await page.request.post("/api/v1/auth/login", {
        form: { username: email, password: wrongPassword },
      })
      if (attempt < LOCKOUT_ATTEMPTS) {
        expect(response.status(), `failed credential attempt ${attempt}`).toBe(401)
        continue
      }

      expect(response.status(), "the configured threshold locks only this synthetic account").toBe(
        423
      )
      const retryAfter = Number(response.headers()["retry-after"])
      expect(Number.isInteger(retryAfter) && retryAfter > 0 && retryAfter <= 30).toBe(true)
    }
  } finally {
    try {
      if (createdUserId) await deleteOwnedAccount(adminPage, createdUserId)
    } finally {
      await adminContext.close()
    }
  }
})
