import type { Page } from "@playwright/test"
import {
  expect,
  freshPassword,
  loginAs,
  loginWith,
  stubBreachedPasswordLookup,
  test,
} from "./fixtures"

interface OwnerProfileResponse {
  id: string
  email: string
  full_name: string | null
}

interface AdminUserRow {
  id: string
  email: string
  full_name: string | null
}

const waitForPasswordChange = (page: Page) =>
  page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/users/me/password" &&
      response.request().method() === "POST"
  )

const readOwnerProfile = async (page: Page): Promise<OwnerProfileResponse> => {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.status(), "the signed-in synthetic user can read its own profile").toBe(200)
  return (await response.json()) as OwnerProfileResponse
}

const openPasswordSection = async (page: Page): Promise<void> => {
  const section = page.getByRole("button", { name: /Пароль/u })
  await expect(section).toBeVisible()
  if ((await section.getAttribute("aria-expanded")) !== "true") await section.click()
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
    "the generated identity must resolve to at most one account"
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
    const result = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await result.json().catch(() => null)) as { deleted?: boolean } | null
    return { status: result.status, deleted: body?.deleted === true }
  }, match.id)
  expect(deletion.status, "cleanup uses the CSRF-protected admin endpoint").toBe(200)
  expect(deletion.deleted, "cleanup deletes only the exact generated account id").toBe(true)
}

test("password settings reject a wrong current password and persist a corrected change", async ({
  page,
  browser,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = crypto.randomUUID()
  const email = `live-password-settings-${testInfo.project.name}-${identity}@university.dev`
  const fullName = `Live Password Settings ${testInfo.project.name} ${identity}`
  const currentPassword = freshPassword()
  const incorrectCurrentPassword = `${currentPassword}-incorrect`
  const updatedPassword = freshPassword()
  let registrationAttempted = false

  const adminContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminPage = await adminContext.newPage()
  let passwordChangeRequests = 0
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/v1/users/me/password"
    ) {
      passwordChangeRequests += 1
    }
  })

  try {
    await loginAs(adminPage, "admin")
    await stubBreachedPasswordLookup(page)

    await page.goto("/register")
    await page.getByLabel("Имя", { exact: true }).fill(fullName)
    await page.getByRole("textbox", { name: "E-mail" }).fill(email)
    await page.getByLabel("Пароль", { exact: true }).fill(currentPassword)
    await page.getByLabel("Повторите пароль", { exact: true }).fill(currentPassword)
    registrationAttempted = true
    await page.getByRole("button", { name: "Зарегистрироваться" }).click()
    await expect(page).toHaveURL(/\/login$/u)
    await loginWith(page, email, currentPassword)

    const createdProfile = await readOwnerProfile(page)
    expect(createdProfile.email).toBe(email)
    expect(createdProfile.full_name).toBe(fullName)

    await page.goto("/settings?tab=2")
    await openPasswordSection(page)
    const currentPasswordField = page.getByLabel("Текущий пароль", { exact: true })
    const newPasswordField = page.getByLabel("Новый пароль", { exact: true })
    const confirmPasswordField = page.getByLabel("Повторите новый пароль", { exact: true })
    const updatePasswordButton = page.getByRole("button", { name: "Обновить пароль", exact: true })

    await currentPasswordField.fill(incorrectCurrentPassword)
    await newPasswordField.fill(updatedPassword)
    await confirmPasswordField.fill(updatedPassword)
    const failedResponseWait = waitForPasswordChange(page)
    await updatePasswordButton.click()
    const failedResponse = await failedResponseWait
    expect(failedResponse.status(), "the server rejects an incorrect current password").toBe(400)
    await expect(currentPasswordField).toHaveAttribute("aria-invalid", "true")
    await expect(page.getByRole("alert")).toContainText("Текущий пароль указан неверно")
    expect(passwordChangeRequests).toBe(1)

    await page.reload()
    const stillSignedInProfile = await readOwnerProfile(page)
    expect(stillSignedInProfile.email).toBe(email)
    await openPasswordSection(page)
    const reloadedPasswordInputValues = await Promise.all([
      currentPasswordField.inputValue(),
      newPasswordField.inputValue(),
      confirmPasswordField.inputValue(),
    ])
    const passwordInputsAreCleared = reloadedPasswordInputValues.every((value) => value === "")
    const passwordErrorIsCleared = (await page.getByRole("alert").count()) === 0
    const passwordFormRestoredAfterReload =
      passwordInputsAreCleared &&
      passwordErrorIsCleared &&
      (await currentPasswordField.getAttribute("aria-invalid")) !== "true"
    expect(
      passwordFormRestoredAfterReload,
      "reload restores the original empty password form after server rejection without revealing field values"
    ).toBe(true)

    const verificationContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    try {
      const verificationPage = await verificationContext.newPage()
      await loginWith(verificationPage, email, currentPassword)
    } finally {
      await verificationContext.close()
    }

    await page.goto("/settings?tab=2")
    await openPasswordSection(page)
    await page.getByLabel("Текущий пароль", { exact: true }).fill(currentPassword)
    await page.getByLabel("Новый пароль", { exact: true }).fill(updatedPassword)
    await page.getByLabel("Повторите новый пароль", { exact: true }).fill(updatedPassword)
    const savedResponseWait = waitForPasswordChange(page)
    await page.getByRole("button", { name: "Обновить пароль", exact: true }).click()
    const savedResponse = await savedResponseWait
    expect(savedResponse.status(), "a corrected password change is saved by the real API").toBe(200)
    expect(passwordChangeRequests).toBe(2)

    await page.reload()
    const reloadedProfile = await readOwnerProfile(page)
    expect(reloadedProfile.email).toBe(email)

    const updatedContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    try {
      const updatedPage = await updatedContext.newPage()
      await loginWith(updatedPage, email, updatedPassword)
    } finally {
      await updatedContext.close()
    }

    expect(createdProfile.id).toMatch(/^[0-9a-f-]{36}$/iu)
  } finally {
    try {
      if (registrationAttempted) await deleteOnlyCreatedAccount(adminPage, email, fullName)
    } finally {
      await adminContext.close()
    }
  }
})
