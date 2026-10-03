import { expect, loginAs, test } from "./fixtures"

test("admin can open secure audit logs and read the live audit endpoint", async ({ page }) => {
  await loginAs(page, "admin")

  await page.goto("/admin/audit")
  await expect(page).toHaveURL(/\/admin\/audit$/u)
  await expect(
    page.getByRole("heading", {
      level: 1,
      name: /Secure Audit Logs|Защищённый аудит/iu,
    })
  ).toBeVisible()

  const response = await page.request.get("/api/v1/admin/audit?limit=1&offset=0")
  expect(response.status(), "admin GET /api/v1/admin/audit should be allowed").toBe(200)
  const auditPage = (await response.json()) as { items?: unknown[]; total?: unknown }
  expect(Array.isArray(auditPage.items), "audit API returns its paginated items").toBe(true)
  expect(Number.isInteger(auditPage.total), "audit API returns a total count").toBe(true)
})

for (const role of ["student", "teacher"] as const) {
  test(`${role} is denied the secure audit logs page and API`, async ({ page }) => {
    await loginAs(page, role)

    const identity = await page.request.get("/api/v1/users/me")
    expect(identity.status(), `${role} fixture must be authenticated`).toBe(200)
    expect((await identity.json()).role, `${role} fixture role`).toBe(role)

    await page.goto("/admin/audit")
    await expect(page, `${role} should be redirected from /admin/audit`).toHaveURL(/\/dashboard$/u)

    const response = await page.request.get("/api/v1/admin/audit?limit=1&offset=0")
    expect(response.status(), `${role} GET /api/v1/admin/audit status`).toBe(403)
  })
}
