import { expect, loginAs, ROLES, test } from "./fixtures"

const directoryRoles = ["student", "teacher", "admin"] as const

type UserDirectoryEntry = {
  email: string
  role: (typeof directoryRoles)[number]
  recovery_codes_left: number
}

// These names come from the backend auth DTOs/models and identity schemas.
// recovery_codes_left is deliberately absent: it is a count, not a credential.
const credentialFieldNames = new Set([
  "password",
  "hashedpassword",
  "passwordhash",
  "secret",
  "totpsecret",
  "otpsecret",
  "token",
  "tokenhash",
  "tokendigest",
  "otpdigest",
  "accesstoken",
  "refreshtoken",
  "signingkey",
  "codehash",
  "recoverycode",
  "recoverycodes",
  "authorization",
  "cookie",
])

function assertNoCredentialFields(value: unknown, responseDescription: string): void {
  const visit = (current: unknown, path: string): void => {
    if (Array.isArray(current)) {
      current.forEach((entry, index) => visit(entry, `${path}[${index}]`))
      return
    }
    if (current === null || typeof current !== "object") return

    for (const [field, nested] of Object.entries(current)) {
      const normalizedField = field.toLowerCase().replace(/[_-]/gu, "")
      expect(
        credentialFieldNames.has(normalizedField),
        `${responseDescription} exposed credential field ${path}.${field}`
      ).toBe(false)
      visit(nested, `${path}.${field}`)
    }
  }

  visit(value, "$")
}

test("admin filters the live users directory by role without changing records", async ({
  page,
}) => {
  await loginAs(page, "admin")

  const mutatingRequests: string[] = []
  page.on("request", (request) => {
    const requestUrl = new URL(request.url())
    if (
      ["/api/v1/users", "/api/v1/groups"].includes(requestUrl.pathname) &&
      !["GET", "HEAD"].includes(request.method())
    ) {
      mutatingRequests.push(`${request.method()} ${requestUrl.pathname}`)
    }
  })

  await page.goto("/admin/users")
  await expect(page).toHaveURL(/\/admin\/users$/u)
  await expect(page.getByRole("heading", { level: 1, name: /Пользователи|Users/u })).toBeVisible()

  const roleFilter = page.locator("#role-filter")
  for (const role of directoryRoles) {
    const filteredResponse = page.waitForResponse((response) => {
      const requestUrl = new URL(response.url())
      return requestUrl.pathname === "/api/v1/users" && requestUrl.searchParams.get("role") === role
    })
    await roleFilter.selectOption(role)

    const response = await filteredResponse
    expect(response.status(), `admin GET /api/v1/users?role=${role} should be allowed`).toBe(200)
    const payload: unknown = await response.json()
    assertNoCredentialFields(payload, `admin GET /api/v1/users?role=${role}`)
    expect(Array.isArray(payload)).toBe(true)
    const records = payload as UserDirectoryEntry[]
    expect(records.length, `the seeded ${role} account should be listed`).toBeGreaterThan(0)
    expect(records.every((record) => record.role === role)).toBe(true)
    expect(
      records.every(
        (record) => Number.isInteger(record.recovery_codes_left) && record.recovery_codes_left >= 0
      )
    ).toBe(true)
    expect(records.some((record) => record.email === ROLES[role].email)).toBe(true)
    await expect(
      page.getByText(ROLES[role].email, { exact: true }).filter({ visible: true })
    ).toBeVisible()

    for (const otherRole of directoryRoles.filter((candidate) => candidate !== role)) {
      await expect(
        page.getByText(ROLES[otherRole].email, { exact: true }).filter({ visible: true })
      ).toHaveCount(0)
    }
  }

  expect(mutatingRequests).toEqual([])
})

for (const role of ["student", "teacher"] as const) {
  test(`${role} cannot access the admin users page or full directory`, async ({ page }) => {
    await loginAs(page, role)

    const identity = await page.request.get("/api/v1/users/me")
    expect(identity.status(), `${role} identity should remain authenticated`).toBe(200)
    expect((await identity.json()).role, `${role} synthetic fixture role`).toBe(role)

    await page.goto("/admin/users")
    await expect(page, `${role} should be redirected from /admin/users`).toHaveURL(/\/dashboard$/u)

    const users = await page.request.get("/api/v1/users")
    expect(users.status(), `${role} GET /api/v1/users status`).toBe(403)

    const filteredUsers = await page.request.get("/api/v1/users?role=admin")
    expect(filteredUsers.status(), `${role} GET /api/v1/users?role=admin status`).toBe(403)
  })
}
