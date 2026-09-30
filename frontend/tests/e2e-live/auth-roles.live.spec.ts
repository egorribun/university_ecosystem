import { expect, loginAs, ROLES, submitLogin, test, type Role } from "./fixtures"

const ROLE_NAMES: Role[] = ["student", "teacher", "admin"]

for (const role of ROLE_NAMES) {
  test(`${role} signs in against the real backend and reaches the dashboard`, async ({ page }) => {
    await loginAs(page, role)

    await expect(page.getByRole("heading", { level: 1 })).toBeVisible()
    const me = await page.request.get("/api/v1/users/me")
    expect(me.ok()).toBe(true)
    expect((await me.json()).email).toBe(ROLES[role].email)
  })
}

test("a wrong password keeps the user on the login page", async ({ page }) => {
  await submitLogin(page, ROLES.student.email, "definitely-not-the-password")

  await expect(page.getByRole("alert")).toBeVisible()
  await expect(page).toHaveURL(/\/login/)
  const me = await page.request.get("/api/v1/users/me")
  expect(me.status()).toBe(401)
})

test("admin can access the admin page and user listing", async ({ page }) => {
  await loginAs(page, "admin")
  await page.goto("/admin/users")
  await expect(page).toHaveURL(/\/admin\/users/)
  await expect(
    page.getByText(ROLES.teacher.email, { exact: true }).filter({ visible: true })
  ).toBeVisible()

  const adminUsers = await page.request.get("/api/v1/users")
  expect(adminUsers.status(), "admin GET /api/v1/users should be allowed").toBe(200)
  const adminUserRecords = (await adminUsers.json()) as { email: string }[]
  expect(
    adminUserRecords.some((user) => user.email === ROLES.teacher.email),
    "admin user listing should include the seeded teacher"
  ).toBe(true)
})

for (const role of ["student", "teacher"] as const) {
  test(`${role} is denied access to admin pages and user listing`, async ({ page }) => {
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
  })
}
