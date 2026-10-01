import { expect, ROLES, test } from "./fixtures"

const untrustedRedirectTargets = [
  {
    label: "an absolute external URL",
    target: "https://redirect-target.invalid/landing",
  },
  {
    label: "a protocol-relative URL",
    target: "//redirect-target.invalid/landing",
  },
  {
    label: "a slash-backslash URL normalized as an external URL by browsers",
    target: "/\\redirect-target.invalid/landing",
  },
] as const

for (const { label, target } of untrustedRedirectTargets) {
  test(`seeded login keeps ${label} on the same origin`, async ({ page }) => {
    // Navigate directly so the unsafe redirect query reaches the real Login
    // route; fixtures' login helpers intentionally navigate to plain /login.
    await page.goto(`/login?redirect=${encodeURIComponent(target)}`)
    const loginUrl = new URL(page.url())
    expect(loginUrl.pathname).toBe("/login")
    expect(loginUrl.searchParams.get("redirect")).toBe(target)

    // Submit the actual form with the disposable live-stand student account.
    await expect(page.getByRole("textbox", { name: "E-mail" })).toBeVisible()
    await page.getByRole("textbox", { name: "E-mail" }).fill(ROLES.student.email)
    await page.getByLabel("Пароль", { exact: true }).fill(ROLES.student.password)
    await page.getByRole("button", { name: "Войти" }).click()

    await expect(page).toHaveURL(new URL("/dashboard", loginUrl.origin).href)
    expect(new URL(page.url()).origin).toBe(loginUrl.origin)
  })
}
