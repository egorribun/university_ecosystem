import type { Page } from "@playwright/test"
import { reportLiveProfileSaveFailure } from "./profile-save-diagnostic"
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
  pending_email?: string | null
  role: string
  full_name: string | null
  profile_detail: { about: string | null } | null
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

const readOwnerProfile = async (page: Page): Promise<OwnerProfileResponse> => {
  const response = await page.request.get("/api/v1/users/me")
  expect(response.status(), "the signed-in synthetic user can read its own profile").toBe(200)
  return (await response.json()) as OwnerProfileResponse
}

const ownerAbout = (profile: OwnerProfileResponse): string => profile.profile_detail?.about ?? ""

const deleteOnlyCreatedAccount = async (
  adminPage: Page,
  email: string,
  possibleNames: string[],
  createdUserId?: string
): Promise<void> => {
  let userId = createdUserId
  if (!userId) {
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
            (entry) =>
              entry.email === email && entry.full_name && expectedNames.has(entry.full_name)
          )
          .map((entry) => [entry.id, entry] as const)
      ).values(),
    ]
    expect(
      matchesById.length,
      "the generated identity must resolve to at most one account"
    ).toBeLessThanOrEqual(1)

    userId = matchesById[0]?.id
  }
  if (!userId) return

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
  }, userId)

  expect(deletion.status, "cleanup targets only the generated synthetic account").toBe(200)
  expect(deletion.deleted).toBe(true)
}

test("profile editor cancellation and rejected oversized save preserve values before success", async ({
  page,
  browser,
  pageErrors,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = crypto.randomUUID()
  const initialName = `Live Profile ${testInfo.project.name} ${identity}`
  const cancelledName = `${initialName} Unsaved`
  const rejectedName = `${initialName} Rejected`
  const updatedName = `${initialName} Updated`
  const email = `live-profile-${testInfo.project.name}-${identity}@university.dev`
  const about = `Synthetic profile acceptance ${identity}`
  const oversizedAbout = "x".repeat(4097)
  const password = freshPassword()
  let registrationAttempted = false

  const adminContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminPage = await adminContext.newPage()
  let profileUpdateRequests = 0
  const profileMutationPaths: string[] = []
  page.on("request", (request) => {
    if (request.method() === "PUT" && new URL(request.url()).pathname === "/api/v1/users/me") {
      profileUpdateRequests += 1
    }
  })

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
    await expect(page).toHaveURL(/\/login/u)
    await loginWith(page, email, password)

    const createdProfile = await readOwnerProfile(page)
    expect(createdProfile.email).toBe(email)
    expect(createdProfile.role).toBe("student")
    expect(createdProfile.full_name).toBe(initialName)
    const initialAbout = ownerAbout(createdProfile)
    page.on("request", (request) => {
      const path = new URL(request.url()).pathname
      if (
        path.startsWith("/api/v1/") &&
        ["POST", "PUT", "PATCH", "DELETE"].includes(request.method())
      ) {
        profileMutationPaths.push(`${request.method()} ${path}`)
      }
    })

    await page.goto("/profile?edit=1")
    const nameField = page.getByLabel("Имя", { exact: true })
    const aboutField = page.getByLabel("О себе", { exact: true })
    await expect(nameField).toHaveValue(initialName)
    await expect(aboutField).toHaveValue(initialAbout)

    const cancelledAbout = `Unsaved profile edit ${identity}`
    await nameField.fill(cancelledName)
    await aboutField.fill(cancelledAbout)
    await page.getByRole("button", { name: "ОТМЕНА", exact: true }).click()
    await expect(page).toHaveURL(/\/profile$/u)
    await expect(page.getByRole("heading", { level: 1, name: initialName })).toBeVisible()
    expect(profileUpdateRequests).toBe(0)

    const cancelledProfile = await readOwnerProfile(page)
    expect(cancelledProfile.full_name).toBe(initialName)
    expect(ownerAbout(cancelledProfile)).toBe(initialAbout)

    await page.reload()
    const cancelledProfileAfterReload = await readOwnerProfile(page)
    expect(cancelledProfileAfterReload.full_name).toBe(initialName)
    expect(ownerAbout(cancelledProfileAfterReload)).toBe(initialAbout)
    expect(profileUpdateRequests).toBe(0)

    await page.goto("/profile?edit=1")
    await expect(nameField).toHaveValue(initialName)
    await expect(aboutField).toHaveValue(initialAbout)

    await nameField.fill(rejectedName)
    await aboutField.fill(oversizedAbout)
    const rejectedSaveResponsePromise = waitForProfileUpdate(page)
    await page.getByRole("button", { name: "СОХРАНИТЬ", exact: true }).click()
    const rejectedSaveResponse = await rejectedSaveResponsePromise
    expect(
      rejectedSaveResponse.status(),
      "the database-bound profile field rejects a value beyond its supported size"
    ).toBeGreaterThanOrEqual(400)
    const profileFeedback = page.getByTestId("profile-save-feedback")
    try {
      await expect(profileFeedback.getByRole("alert")).toBeVisible()
    } catch (assertionError) {
      const responseBody = await rejectedSaveResponse.json().catch(() => undefined)
      const alertCount = await profileFeedback
        .getByRole("alert")
        .count()
        .catch(() => undefined)
      const saveButton = page.getByRole("button", { name: "СОХРАНИТЬ", exact: true })
      const saveButtonCount = await saveButton.count().catch(() => 0)
      const saveDisabled =
        saveButtonCount === 1 ? await saveButton.isDisabled().catch(() => undefined) : undefined
      let pathname: string | undefined
      try {
        pathname = new URL(page.url()).pathname
      } catch {
        // An unavailable URL is reduced to the fixed "other" route family.
      }
      try {
        reportLiveProfileSaveFailure({
          project: testInfo.project.name,
          status: rejectedSaveResponse.status(),
          body: responseBody,
          alertCount,
          saveDisabled,
          pathname,
          pageErrors,
        })
      } catch {
        // Diagnostics must never replace the original alert assertion.
      }
      throw assertionError
    }
    await expect(nameField).toHaveValue(rejectedName)
    const retainedDraft = await aboutField.inputValue()
    expect(retainedDraft.length).toBe(oversizedAbout.length)
    expect(retainedDraft === oversizedAbout).toBe(true)
    await expect(page.getByRole("button", { name: "СОХРАНИТЬ", exact: true })).toBeVisible()
    const rejectedProfile = await readOwnerProfile(page)
    expect(rejectedProfile.full_name).toBe(initialName)
    expect(ownerAbout(rejectedProfile)).toBe(initialAbout)
    expect(profileUpdateRequests).toBe(1)

    await nameField.fill(updatedName)
    await aboutField.fill(about)
    const saveResponse = waitForProfileUpdate(page)
    await page.getByRole("button", { name: "СОХРАНИТЬ", exact: true }).click()
    const savedResponse = await saveResponse
    expect(savedResponse.status(), "profile edits persist through /users/me").toBe(200)
    expect(profileUpdateRequests).toBe(2)
    expect(profileMutationPaths).toEqual(["PUT /api/v1/users/me", "PUT /api/v1/users/me"])
    await expect(page).toHaveURL(/\/profile$/u)
    await expect(page.getByRole("heading", { level: 1, name: updatedName })).toBeVisible()

    const savedProfile = await readOwnerProfile(page)
    expect(savedProfile.full_name).toBe(updatedName)
    expect(savedProfile.profile_detail?.about).toBe(about)

    await page.reload()
    await expect(page.getByRole("heading", { level: 1, name: updatedName })).toBeVisible()
    const reloadedProfile = await readOwnerProfile(page)
    expect(reloadedProfile.full_name).toBe(updatedName)
    expect(reloadedProfile.profile_detail?.about).toBe(about)

    await page.goto("/profile?edit=1")
    await expect(page.getByLabel("Имя", { exact: true })).toHaveValue(updatedName)
    await expect(page.getByLabel("О себе", { exact: true })).toHaveValue(about)
    expect(reloadedProfile.id).toMatch(/^[0-9a-f-]{36}$/iu)
  } finally {
    try {
      if (registrationAttempted) {
        await deleteOnlyCreatedAccount(adminPage, email, [
          initialName,
          cancelledName,
          rejectedName,
          updatedName,
        ])
      }
    } finally {
      await adminContext.close()
    }
  }
})

test("profile API rejects email changes outside the verified change flow", async ({
  page,
  browser,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = crypto.randomUUID()
  const fullName = `Live Profile Email Guard ${testInfo.project.name} ${identity}`
  const email = `live-profile-email-guard-${testInfo.project.name}-${identity}@university.dev`
  const attemptedEmail = `live-profile-email-target-${testInfo.project.name}-${identity}@university.dev`
  const password = freshPassword()
  let registrationAttempted = false
  let createdUserId: string | undefined

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

    const profileBeforeAttempt = await readOwnerProfile(page)
    expect(profileBeforeAttempt.email).toBe(email)
    expect(profileBeforeAttempt.pending_email).toBeNull()
    expect(profileBeforeAttempt.role).toBe("student")
    expect(profileBeforeAttempt.id).toMatch(/^[0-9a-f-]{36}$/iu)
    createdUserId = profileBeforeAttempt.id

    const attemptedStatus = await page.evaluate(async (candidateEmail) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return 0

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const response = await fetch("/api/v1/users/me", {
        method: "PUT",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ email: candidateEmail }),
      })
      return response.status
    }, attemptedEmail)

    expect(
      attemptedStatus,
      "a valid-CSRF profile request cannot bypass the dedicated email-confirmation endpoint"
    ).toBe(422)

    const profileAfterAttempt = await readOwnerProfile(page)
    expect(profileAfterAttempt.email).toBe(profileBeforeAttempt.email)
    expect(profileAfterAttempt.pending_email).toBe(profileBeforeAttempt.pending_email)
  } finally {
    try {
      if (registrationAttempted) {
        await deleteOnlyCreatedAccount(adminPage, email, [fullName], createdUserId)
      }
    } finally {
      await adminContext.close()
    }
  }
})
