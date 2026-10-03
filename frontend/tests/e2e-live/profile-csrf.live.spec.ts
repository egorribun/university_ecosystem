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

const waitForProfileUpdate = (page: Page) =>
  page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/users/me" &&
      response.request().method() === "PUT"
  )

const waitForCsrfCookieBootstrap = (page: Page) =>
  page.waitForResponse(
    (response) =>
      new URL(response.url()).pathname === "/api/v1/auth/csrf-cookie" &&
      response.request().method() === "GET"
  )

const readOwnerProfile = async (page: Page): Promise<OwnerProfileResponse> => {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.status(), "the signed-in synthetic user can read its own profile").toBe(200)
  return (await response.json()) as OwnerProfileResponse
}

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  possibleNames: string[]
): Promise<void> => {
  const userPages = await Promise.all(
    possibleNames.map(async (fullName) => {
      const query = new URLSearchParams({ search: fullName, limit: "200" })
      const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
      expect(response.status(), "admin can locate the test-owned synthetic account").toBe(200)
      return (await response.json()) as AdminUserRow[]
    })
  )
  const expectedNames = new Set(possibleNames)
  const matchesById = [
    ...new Map(
      userPages
        .flat()
        .filter(
          (entry) => entry.email === email && entry.full_name && expectedNames.has(entry.full_name)
        )
        .map((entry) => [entry.id, entry] as const)
    ).values(),
  ]
  expect(
    matchesById.length,
    "the generated identity resolves to at most one account"
  ).toBeLessThanOrEqual(1)

  const [match] = matchesById
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

  expect(deletion.status, "cleanup deletes only the exact generated user id").toBe(200)
  expect(deletion.deleted).toBe(true)
}

test.use({ trace: "off", screenshot: "off" })

test("authenticated profile update rejects missing and invalid CSRF proof", async ({
  page,
  browser,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = crypto.randomUUID()
  const initialName = `Live CSRF Profile ${testInfo.project.name} ${identity}`
  const missingHeaderName = `${initialName} Missing Header`
  const invalidProofName = `${initialName} Invalid Proof`
  const acceptedName = `${initialName} Accepted`
  const email = `live-profile-csrf-${testInfo.project.name}-${identity}@university.dev`
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
    await page.getByLabel("Имя", { exact: true }).fill(initialName)
    await page.getByRole("textbox", { name: "E-mail" }).fill(email)
    await page.getByLabel("Пароль", { exact: true }).fill(password)
    await page.getByLabel("Повторите пароль", { exact: true }).fill(password)
    registrationAttempted = true
    await page.getByRole("button", { name: "Зарегистрироваться" }).click()
    await expect(page).toHaveURL(/\/login$/u)
    await loginWith(page, email, password)

    const ownerProfile = await readOwnerProfile(page)
    expect(ownerProfile.email).toBe(email)
    expect(ownerProfile.full_name).toBe(initialName)

    const cookieNames = (await page.context().cookies()).map((cookie) => cookie.name)
    expect(cookieNames).toContain("access_token_v2")
    expect(cookieNames).toContain("csrf_token")

    const missingCsrfStatus = await page.evaluate(async (candidateName) => {
      const response = await fetch("/api/v1/users/me", {
        method: "PUT",
        credentials: "same-origin",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ full_name: candidateName }),
      })
      return response.status
    }, missingHeaderName)
    expect(missingCsrfStatus, "missing CSRF header is rejected").toBe(403)
    expect((await readOwnerProfile(page)).full_name).toBe(initialName)

    const invalidCsrfAttempt = await page.evaluate(async (candidateName) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) {
        return { status: 0, cookiePresent: false, proofMatchesCookie: false }
      }

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const forgedToken = `${csrfToken}.invalid`
      const secureAttribute = location.protocol === "https:" ? "; Secure" : ""
      document.cookie = `csrf_token=${encodeURIComponent(forgedToken)}; Path=/; SameSite=Lax${secureAttribute}`
      const installedCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      const installedToken = installedCookie
        ? decodeURIComponent(installedCookie.slice("csrf_token=".length))
        : null
      const response = await fetch("/api/v1/users/me", {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": forgedToken,
        },
        body: JSON.stringify({ full_name: candidateName }),
      })
      document.cookie = `csrf_token=; Max-Age=0; Path=/; SameSite=Lax${secureAttribute}`
      const cookieAfterDeletion = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      const missingCookieAbsent = cookieAfterDeletion === undefined
      const missingCookieResponse = await fetch("/api/v1/users/me", {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ full_name: candidateName }),
      })
      document.cookie = `csrf_token=; Max-Age=0; Path=/; SameSite=Lax${secureAttribute}`
      const cookieAfterRejectedRequest = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      return {
        status: response.status,
        cookiePresent: installedToken !== null,
        proofMatchesCookie: installedToken === forgedToken,
        missingCookieStatus: missingCookieResponse.status,
        missingCookieAbsent,
        cookieClearedAfterRejectedRequest: cookieAfterRejectedRequest === undefined,
      }
    }, invalidProofName)
    expect(invalidCsrfAttempt.cookiePresent, "forged proof is installed as a real cookie").toBe(
      true
    )
    expect(
      invalidCsrfAttempt.proofMatchesCookie,
      "forged cookie and header match so the server must validate the signature"
    ).toBe(true)
    expect(invalidCsrfAttempt.status, "invalid signed CSRF proof is rejected").toBe(403)
    expect(
      invalidCsrfAttempt.missingCookieAbsent,
      "the second same-origin mutation is sent after removing the CSRF cookie"
    ).toBe(true)
    expect(
      invalidCsrfAttempt.missingCookieStatus,
      "a valid header without its CSRF cookie is rejected"
    ).toBe(403)
    expect(
      invalidCsrfAttempt.cookieClearedAfterRejectedRequest,
      "the rejection response does not leave a generated CSRF cookie for later UI recovery"
    ).toBe(true)
    expect((await readOwnerProfile(page)).full_name).toBe(initialName)

    await page.goto("/profile?edit=1")
    await page.getByLabel("Имя", { exact: true }).fill(acceptedName)
    await page.context().clearCookies({ name: "csrf_token" })
    const cookiesAfterExpiry = (await page.context().cookies()).map((cookie) => cookie.name)
    expect(cookiesAfterExpiry, "only the CSRF cookie is removed before UI recovery").not.toContain(
      "csrf_token"
    )
    expect(cookiesAfterExpiry, "the authenticated session remains available").toContain(
      "access_token_v2"
    )
    const csrfBootstrapResponsePromise = waitForCsrfCookieBootstrap(page)
    const saveResponsePromise = waitForProfileUpdate(page)
    await page.getByRole("button", { name: "СОХРАНИТЬ", exact: true }).click()
    const [csrfBootstrapResponse, saveResponse] = await Promise.all([
      csrfBootstrapResponsePromise,
      saveResponsePromise,
    ])
    expect(csrfBootstrapResponse.status(), "the UI reacquires the CSRF cookie before saving").toBe(
      200
    )
    expect((await page.context().cookies()).map((cookie) => cookie.name)).toContain("csrf_token")
    expect(saveResponse.status(), "the normal same-origin UI mutation succeeds").toBe(200)
    await expect(page).toHaveURL(/\/profile$/u)
    await expect(page.getByRole("heading", { level: 1, name: acceptedName })).toBeVisible()

    expect((await readOwnerProfile(page)).full_name).toBe(acceptedName)
    await page.reload()
    await expect(page.getByRole("heading", { level: 1, name: acceptedName })).toBeVisible()
    expect((await readOwnerProfile(page)).full_name).toBe(acceptedName)
  } finally {
    try {
      if (registrationAttempted) {
        await deleteOnlyCreatedAccount(adminPage, email, [
          initialName,
          missingHeaderName,
          invalidProofName,
          acceptedName,
        ])
      }
    } finally {
      await adminContext.close()
    }
  }
})
