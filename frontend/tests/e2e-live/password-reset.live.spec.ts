import { randomUUID } from "node:crypto"
import type { Page } from "@playwright/test"
import {
  awaitMail,
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
  submitLogin,
  test,
} from "./fixtures"

const RESET_LINK = /\/reset-password\?token=([\w.~-]+)/
const UNTRUSTED_REDIRECT = "https://redirect-target.invalid/landing"

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
  browser,
  page,
}, testInfo) => {
  await stubBreachedPasswordLookup(page)
  const email = `live-reset-${testInfo.project.name}-${randomUUID()}@university.dev`
  const firstPassword = freshPassword()
  const newPassword = freshPassword()
  let createdUserId: string | null = null

  try {
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
    createdUserId = registrationBody.id

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
      return (
        current.pathname === "/reset-password" && current.searchParams.get("redirect") === target
      )
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
    const replayResponse = page.waitForResponse(
      (response) =>
        response.request().method() === "POST" &&
        new URL(response.url()).pathname.endsWith("/password/reset")
    )
    await page.getByRole("button", { name: "Сохранить пароль" }).click()
    const replayResult = await replayResponse
    expect(replayResult.status(), "a consumed reset token must be rejected by the API").toBe(400)
    // Scope to the reset form so the app's empty global live region cannot
    // satisfy this assertion before the consumed-token error is rendered.
    const replayAlert = page
      .locator("form")
      .filter({ has: page.locator("#reset-submit-btn") })
      .getByRole("alert")
    await expect(replayAlert).toBeVisible()
    const replayFeedback = await replayAlert.evaluate(
      (alert, resetToken) => ({
        isNonEmpty: Boolean(alert.textContent?.trim()),
        containsResetToken: alert.textContent?.includes(resetToken) ?? false,
      }),
      token
    )
    expect(replayFeedback.isNonEmpty).toBe(true)
    expect(replayFeedback.containsResetToken).toBe(false)
    await expect(page.getByText("Пароль обновлён")).toBeHidden()
    await submitLogin(page, email, replayPassword)
    await expect(page).toHaveURL(/\/login/)
  } finally {
    if (createdUserId) {
      const cleanupContext = await browser.newContext({
        baseURL: process.env.LIVE_BASE_URL,
        ignoreHTTPSErrors: true,
        locale: "ru-RU",
      })
      try {
        const cleanupPage = await cleanupContext.newPage()
        await loginAs(cleanupPage, "admin")
        const cleanup = await cleanupPage.evaluate(async (userId) => {
          const csrfCookie = document.cookie
            .split(";")
            .map((part) => part.trim())
            .find((part) => part.startsWith("csrf_token="))
          if (!csrfCookie) return { status: 0 }

          const response = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
            method: "DELETE",
            credentials: "same-origin",
            headers: {
              Accept: "application/json",
              "X-CSRF-Token": decodeURIComponent(csrfCookie.slice("csrf_token=".length)),
              "X-Requested-With": "XMLHttpRequest",
            },
          })
          return { status: response.status }
        }, createdUserId)
        // Keep cleanup failures visible without replacing an earlier reset failure.
        expect.soft(cleanup.status).toBe(200)
      } finally {
        await cleanupContext.close()
      }
    }
  }
})
