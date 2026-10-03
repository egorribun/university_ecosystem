import type { Response } from "@playwright/test"
import { expect, loginAs, ROLES, test, type Role } from "./fixtures"
import { reportLiveHttpStatus } from "./http-status-diagnostic"

const ROLE_NAMES: Role[] = ["student", "teacher", "admin"]
const WRONG_PASSWORD_CASES = [
  {
    role: "student",
    language: "ru",
    project: "desktop",
    expectedError: "Неверный email или пароль",
  },
  {
    role: "teacher",
    language: "en",
    project: "mobile",
    expectedError: "Incorrect email or password",
  },
] as const

for (const role of ROLE_NAMES) {
  test(`${role} signs in against the real backend and reaches the dashboard`, async ({ page }) => {
    await loginAs(page, role)

    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
    const me = await page.request.get("/api/v1/users/me")
    expect(me.ok()).toBe(true)
    expect((await me.json()).email).toBe(ROLES[role].email)
  })
}

test.describe("localized rejected-login acceptance", () => {
  test.describe.configure({ retries: 0 })

  for (const { role, language, project, expectedError } of WRONG_PASSWORD_CASES) {
    test(`${role} receives generic ${language} feedback for one rejected login`, async ({
      page,
      context,
    }, testInfo) => {
      test.skip(
        testInfo.project.name !== project,
        "Run only one rejected login per seeded role in the live matrix."
      )

      const liveBaseUrl = process.env.LIVE_BASE_URL
      if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")
      // Seed both stores before the first document loads. Changing them on an
      // already-open page races its pending language-persistence effect.
      await context.addCookies([{ name: "ue:language", value: language, url: liveBaseUrl }])
      await page.addInitScript((selectedLanguage) => {
        window.localStorage.setItem("ue:language", selectedLanguage)
      }, language)
      await page.goto("/login")
      await page.waitForFunction(() => window.__APP_HYDRATED === true)
      await expect(page.locator("html")).toHaveAttribute("lang", language)

      const identity = ROLES[role].email
      const wrongPassword = "invalid-live-password-for-acceptance" // pragma: allowlist secret -- negative-login test fixture
      await page.locator("#email").fill(identity)
      await page.locator("#password").fill(wrongPassword)
      const loginResponsePromise = page.waitForResponse(
        (response) =>
          response.request().method() === "POST" &&
          new URL(response.url()).pathname === "/api/v1/auth/login"
      )
      await page.locator("#login-submit").click()
      const loginResponse = await loginResponsePromise
      expect(loginResponse.status(), "rejected login must return HTTP 401").toBe(401)

      // The app also has a persistent, empty screen-reader announcer. Verify
      // the submitted form's own error instead of that unrelated live region.
      const feedback = page
        .locator("form")
        .filter({ has: page.locator("#login-submit") })
        .getByRole("alert")
      await expect(feedback).toBeVisible()
      const feedbackText = (await feedback.textContent())?.trim() ?? ""
      const isExactGenericFeedback =
        feedbackText === expectedError &&
        !feedbackText.includes(identity) &&
        !feedbackText.includes(wrongPassword)
      expect(
        isExactGenericFeedback,
        "failed login must show only the locale's generic message without echoing credentials"
      ).toBe(true)

      const visibleText = await page.locator("body").innerText()
      expect(
        !visibleText.includes(identity) && !visibleText.includes(wrongPassword),
        "visible login copy must not echo submitted credentials"
      ).toBe(true)
      expect(new URL(page.url()).pathname).toBe("/login")

      const me = await page.request.get("/api/v1/users/me")
      expect(me.status()).toBe(401)
    })
  }
})

test("admin can access the admin page and user listing", async ({ page }, testInfo) => {
  await loginAs(page, "admin")
  const adminUsers = await page.request.get("/api/v1/users")
  reportLiveHttpStatus(testInfo.project.name, "admin-users", adminUsers.status())
  expect(adminUsers.status(), "admin GET /api/v1/users should be allowed").toBe(200)
  const adminUserRecords = (await adminUsers.json()) as { email: string }[]
  expect(
    adminUserRecords.some((user) => user.email === ROLES.teacher.email),
    "admin user listing should include the seeded teacher"
  ).toBe(true)

  await page.goto("/admin/users")
  await expect(page).toHaveURL(/\/admin\/users/)
  await expect(
    page.getByText(ROLES.teacher.email, { exact: true }).filter({ visible: true })
  ).toBeVisible()
})

test("admin can access feature-flag diagnostics", async ({ page }, testInfo) => {
  await loginAs(page, "admin")
  const featureFlags = await page.request.get("/api/v1/admin/feature-flags")
  reportLiveHttpStatus(testInfo.project.name, "admin-feature-flags", featureFlags.status())
  expect(featureFlags.status(), "admin GET /api/v1/admin/feature-flags should be allowed").toBe(200)

  const reportFeatureFlagsResponse = (response: Response) => {
    if (
      response.request().method() === "GET" &&
      new URL(response.url()).pathname === "/api/v1/admin/feature-flags"
    ) {
      reportLiveHttpStatus(testInfo.project.name, "admin-feature-flags-ui", response.status())
    }
  }
  page.on("response", reportFeatureFlagsResponse)
  try {
    await page.goto("/admin/feature-flags")
    await expect(page).toHaveURL(/\/admin\/feature-flags$/)
    await expect(
      page.getByRole("heading", {
        level: 1,
        name: /Feature Flag Diagnostics|Диагностика флагов функций/iu,
      })
    ).toBeVisible()
  } finally {
    page.off("response", reportFeatureFlagsResponse)
  }
})

for (const role of ["student", "teacher"] as const) {
  test(`${role} is denied access to admin pages, user listing, and feature flags`, async ({
    page,
  }) => {
    await loginAs(page, role)

    const identity = await page.request.get("/api/v1/users/me")
    expect(identity.status(), `${role} /api/v1/users/me status`).toBe(200)
    expect((await identity.json()).role, `${role} fixture role`).toBe(role)

    await page.goto("/admin/users")
    await expect(page, `${role} should be redirected from /admin/users to /dashboard`).toHaveURL(
      /\/dashboard$/
    )

    const users = await page.request.get("/api/v1/users")
    expect(users.status(), `${role} GET /api/v1/users status`).toBe(403)

    await page.goto("/admin/feature-flags")
    await expect(
      page,
      `${role} should be redirected from /admin/feature-flags to /dashboard`
    ).toHaveURL(/\/dashboard$/)

    const featureFlags = await page.request.get("/api/v1/admin/feature-flags")
    expect(featureFlags.status(), `${role} GET /api/v1/admin/feature-flags status`).toBe(403)
  })
}
