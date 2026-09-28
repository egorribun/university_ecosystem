import { expect, test as base, type Page } from "@playwright/test"

/**
 * Accounts created by scripts/seed_demo_data.py and scripts/seed_admin_data.py
 * inside the disposable live stand. They exist nowhere else.
 */
export const ROLES = {
  student: {
    email: "test@university.dev",
    password: "TestPass@2024x", // pragma: allowlist secret -- disposable stand seed account
  },
  teacher: {
    email: "olga.morozova@university.dev",
    password: "Teacher@2024test", // pragma: allowlist secret -- disposable stand seed account
  },
  admin: {
    email: "admin@university.dev",
    password: "Admin@2024test", // pragma: allowlist secret -- disposable stand seed account
  },
} as const

export type Role = keyof typeof ROLES

const MAILPIT_URL = process.env.LIVE_MAILPIT_URL ?? "http://127.0.0.1:18025"

export async function loginAs(page: Page, role: Role): Promise<void> {
  const { email, password } = ROLES[role]
  await page.goto("/login")
  await page.getByRole("textbox", { name: "E-mail" }).fill(email)
  await page.getByLabel("Пароль", { exact: true }).fill(password)
  await page.getByRole("button", { name: "Войти" }).click()
  await expect(page).toHaveURL(/\/dashboard$/)
}

export interface MailpitMessage {
  ID: string
  Subject: string
  To: { Address: string }[]
  Created: string
}

/** Newest-first messages addressed to `address` in the stand's Mailpit sink. */
export async function mailFor(address: string): Promise<MailpitMessage[]> {
  const response = await fetch(
    `${MAILPIT_URL}/api/v1/search?query=${encodeURIComponent(`to:${address}`)}`
  )
  expect(response.ok, `Mailpit search failed: ${response.status}`).toBe(true)
  const body = (await response.json()) as { messages: MailpitMessage[] }
  return body.messages
}

export async function mailText(id: string): Promise<string> {
  const response = await fetch(`${MAILPIT_URL}/api/v1/message/${id}`)
  expect(response.ok, `Mailpit message ${id} failed: ${response.status}`).toBe(true)
  const body = (await response.json()) as { Text: string }
  return body.Text
}

/** Fails the test on any uncaught page exception, the live lane's crash signal. */
export const test = base.extend<{ pageErrors: Error[] }>({
  pageErrors: [
    async ({ page }, use) => {
      const errors: Error[] = []
      page.on("pageerror", (error) => errors.push(error))
      await use(errors)
      expect(errors, errors.map((error) => error.message).join("\n")).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
