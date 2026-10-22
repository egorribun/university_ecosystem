import { expect, loginAs, test } from "./fixtures"

test("admin can access feature-flag diagnostics", async ({ page }) => {
  await loginAs(page, "admin")
  await page.goto("/admin/feature-flags")

  await expect(page).toHaveURL(/\/admin\/feature-flags$/u)
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: /Feature Flag Diagnostics|Диагностика флагов функций/iu,
    })
  ).toBeVisible()
  await expect(page.getByRole("note")).toBeVisible()

  const featureFlags = await page.request.get("/api/v1/admin/feature-flags")
  expect(featureFlags.status(), "admin GET /api/v1/admin/feature-flags should be allowed").toBe(200)
  expect(
    Array.isArray(await featureFlags.json()),
    "admin receives read-only flag diagnostics"
  ).toBe(true)
})

for (const role of ["student", "teacher"] as const) {
  test(`${role} is denied access to feature-flag diagnostics`, async ({ page }) => {
    await loginAs(page, role)

    const identity = await page.request.get("/api/v1/users/me")
    expect(identity.status(), `${role} /api/v1/users/me status`).toBe(200)
    expect((await identity.json()).role, `${role} fixture role`).toBe(role)

    await page.goto("/admin/feature-flags")
    await expect(
      page,
      `${role} should be redirected from /admin/feature-flags to /dashboard`
    ).toHaveURL(/\/dashboard$/u)

    const featureFlags = await page.request.get("/api/v1/admin/feature-flags")
    expect(featureFlags.status(), `${role} GET /api/v1/admin/feature-flags status`).toBe(403)

    const rejectedWrite = await page.evaluate(async () => {
      const cookiePrefix = "csrf_token="
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith(cookiePrefix))
      const csrfToken = csrfCookie ? decodeURIComponent(csrfCookie.slice(cookiePrefix.length)) : ""
      if (!csrfToken) throw new Error("the authenticated session must expose its CSRF proof")

      const response = await fetch("/api/v1/admin/feature-flags/rbac-probe-no-such-flag", {
        method: "PATCH",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ enabled: false }),
      })
      return response.status
    })
    expect(
      rejectedWrite,
      `${role} PATCH /api/v1/admin/feature-flags must be forbidden with valid CSRF`
    ).toBe(403)
  })
}
