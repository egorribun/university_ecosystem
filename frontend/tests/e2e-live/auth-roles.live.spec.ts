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

test("the admin area is reachable for an admin and closed to a student", async ({ page }) => {
  await loginAs(page, "admin")
  await page.goto("/admin/users")
  await expect(page).toHaveURL(/\/admin\/users/)
  await expect(
    page.getByText(ROLES.teacher.email, { exact: true }).filter({ visible: true })
  ).toBeVisible()

  await page.context().clearCookies()
  await loginAs(page, "student")
  await page.goto("/admin/users")
  await expect(page).not.toHaveURL(/\/admin\/users/)
  const users = await page.request.get("/api/v1/admin/users")
  expect(users.status()).toBe(403)
})
