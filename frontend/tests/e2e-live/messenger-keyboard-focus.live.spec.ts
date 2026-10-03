import { randomUUID } from "node:crypto"
import type { Page } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
  test,
} from "./fixtures"

interface AdminUserRow {
  id: string
  email: string
  full_name: string | null
}

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  fullName: string
): Promise<void> => {
  const query = new URLSearchParams({ search: fullName, limit: "200" })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  expect(response.status(), "admin can locate the test-owned synthetic account").toBe(200)
  const users = (await response.json()) as AdminUserRow[]
  const matches = users.filter((entry) => entry.email === email && entry.full_name === fullName)
  expect(
    matches.length,
    "the generated identity resolves to at most one account"
  ).toBeLessThanOrEqual(1)

  const [match] = matches
  if (!match) return

  const deletion = await adminPage.evaluate(async (userId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, deleted: false }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await response.json().catch(() => null)) as { deleted?: boolean } | null
    return { status: response.status, deleted: body?.deleted === true }
  }, match.id)

  expect(deletion.status, "cleanup deletes only the exact generated account id").toBe(200)
  expect(deletion.deleted).toBe(true)
}

test("Escape closes the new-chat dialog and restores keyboard focus to its trigger", async ({
  page,
  browser,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = randomUUID()
  const fullName = `Live Messenger keyboard ${testInfo.project.name} ${identity}`
  const email = `live-messenger-keyboard-${testInfo.project.name}-${identity}@university.dev`
  const password = freshPassword()
  let registrationAttempted = false

  const adminContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminPage = await adminContext.newPage()

  try {
    await loginAs(adminPage, "admin")
    await stubBreachedPasswordLookup(page)

    await page.goto("/register")
    await page.getByLabel("Имя", { exact: true }).fill(fullName)
    await page.getByRole("textbox", { name: "E-mail" }).fill(email)
    await page.getByLabel("Пароль", { exact: true }).fill(password)
    await page.getByLabel("Повторите пароль", { exact: true }).fill(password)
    registrationAttempted = true
    await page.getByRole("button", { name: "Зарегистрироваться" }).click()
    await expect(page).toHaveURL(/\/login$/u)
    await loginWith(page, email, password)

    await page.goto("/messenger")
    const newChatTrigger = page.getByRole("button", { name: "Новый чат", exact: true })
    await expect(newChatTrigger).toBeVisible()
    const overflowBeforeDialog = await page
      .locator("body")
      .evaluate((body) => (body as HTMLElement).style.overflow)
    await newChatTrigger.click()

    const dialog = page.getByRole("dialog")
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveAttribute("aria-modal", "true")
    await expect
      .poll(() => page.locator("body").evaluate((body) => (body as HTMLElement).style.overflow))
      .toBe("hidden")

    await page.keyboard.press("Escape")
    await expect(dialog).toHaveCount(0)
    await expect(newChatTrigger).toBeFocused()
    await expect
      .poll(() => page.locator("body").evaluate((body) => (body as HTMLElement).style.overflow))
      .toBe(overflowBeforeDialog)
  } finally {
    try {
      if (registrationAttempted) await deleteOnlyCreatedAccount(adminPage, email, fullName)
    } finally {
      await adminContext.close()
    }
  }
})

test("ArrowDown and ArrowUp navigate search results without opening a chat", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/messenger")

  const newChatTrigger = page.getByRole("button", { name: "Новый чат", exact: true })
  await expect(newChatTrigger).toBeVisible()
  await newChatTrigger.click()

  const dialog = page.getByRole("dialog")
  const search = dialog.getByRole("textbox", { name: "Поиск пользователей", exact: true })
  const userOptions = dialog
    .getByRole("listbox", { name: "Поиск пользователей" })
    .getByRole("option")
  await expect(search).toBeFocused()
  await search.fill("Synthetic Demo")

  const firstOption = userOptions.first()
  await expect(firstOption).toBeVisible()

  await page.keyboard.press("ArrowDown")
  await expect(firstOption).toBeFocused()
  await expect(firstOption).toHaveAttribute("aria-selected", "false")
  await page.keyboard.press("ArrowUp")
  await expect(search).toBeFocused()

  await expect(dialog).toBeVisible()
  await expect(newChatTrigger).toBeVisible()
  await expect(page).toHaveURL(/\/messenger$/u)
})
