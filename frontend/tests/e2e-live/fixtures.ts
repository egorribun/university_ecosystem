import { expect, test as base, type Page } from "@playwright/test"
import {
  createLivePageErrorDiagnostics,
  isLiveAdminNotificationsScenario,
} from "./page-error-diagnostic"
import { requireLiveAdminPassword } from "../../scripts/live-e2e-credentials.mjs"

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
    password: requireLiveAdminPassword(),
  },
} as const

export type Role = keyof typeof ROLES

/** Additional seeded accounts used only to form an isolated live group chat. */
export const GROUP_CHAT_ACCOUNTS = {
  secondMember: {
    email: "ivan.sokolov@university.dev",
    password: "Student@2024test", // pragma: allowlist secret -- disposable stand seed account
  },
  nonMember: {
    email: "sergey.lebedev@university.dev",
    password: "Teacher@2024test", // pragma: allowlist secret -- disposable stand seed account
  },
} as const

/** Stable name lets the live group isolation scenario safely reuse its own group. */
export const LIVE_GROUP_CHAT_NAME = "University Ecosystem live Messenger isolation"

const configuredMailpitURL = process.env.LIVE_MAILPIT_URL
if (!configuredMailpitURL) {
  throw new Error("LIVE_MAILPIT_URL must be set to the endpoint printed by scripts/live_stand.py")
}
const mailpitURL = new URL(configuredMailpitURL)
if (
  mailpitURL.protocol !== "http:" ||
  !["localhost", "127.0.0.1"].includes(mailpitURL.hostname) ||
  mailpitURL.username !== "" ||
  mailpitURL.password !== "" ||
  !mailpitURL.port ||
  Number(mailpitURL.port) < 20_000 ||
  Number(mailpitURL.port) > 45_000 ||
  mailpitURL.pathname !== "/" ||
  mailpitURL.search !== "" ||
  mailpitURL.hash !== ""
) {
  throw new Error("LIVE_MAILPIT_URL must use HTTP and an explicit live-stand loopback port")
}
const MAILPIT_URL = mailpitURL.toString().replace(/\/$/, "")

/** Submits the login form without asserting where it lands. */
export async function submitLogin(page: Page, email: string, password: string): Promise<void> {
  await page.goto("/login")
  await page.getByRole("textbox", { name: "E-mail" }).fill(email)
  await page.getByLabel("Пароль", { exact: true }).fill(password)
  await page.getByRole("button", { name: "Войти" }).click()
}

export async function loginWith(page: Page, email: string, password: string): Promise<void> {
  await submitLogin(page, email, password)
  await expect(page).toHaveURL(/\/dashboard$/)
}

export async function loginAs(page: Page, role: Role): Promise<void> {
  await loginWith(page, ROLES[role].email, ROLES[role].password)
}

/**
 * A unique, strong password for accounts a spec creates itself. The browser's
 * breached-password lookup is stubbed per spec, so it never leaves the stand.
 */
export function freshPassword(): string {
  return `Live-${crypto.randomUUID().slice(0, 12)}-Pw9!`
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

/** Waits for the next message to `address` whose text matches `pattern`. */
export async function awaitMail(address: string, pattern: RegExp): Promise<RegExpMatchArray> {
  let match: RegExpMatchArray | null = null
  await expect
    .poll(
      async () => {
        for (const message of await mailFor(address)) {
          match = (await mailText(message.ID)).match(pattern)
          if (match) return true
        }
        return false
      },
      { message: `no mail to ${address} matching ${pattern}`, timeout: 30_000 }
    )
    .toBe(true)
  return match as unknown as RegExpMatchArray
}

/** Keeps the browser's HIBP range lookup inside the test: every password is unknown. */
export async function stubBreachedPasswordLookup(page: Page): Promise<void> {
  await page.route("https://api.pwnedpasswords.com/**", (route) =>
    route.fulfill({ status: 200, contentType: "text/plain", body: "" })
  )
}

/** Fails the test on any uncaught page exception, the live lane's crash signal. */
export const test = base.extend<{ pageErrors: Error[] }>({
  pageErrors: [
    async ({ page }, use, testInfo) => {
      const errors: Error[] = []
      const isResetScenario =
        (testInfo.project.name === "desktop" || testInfo.project.name === "mobile") &&
        testInfo.file.replace(/\\/g, "/").endsWith("/tests/e2e-live/password-reset.live.spec.ts") &&
        testInfo.title ===
          "a student resets with the Mailpit link without retaining tokens or following hostile redirects"
      const isAdminNotificationsScenario = isLiveAdminNotificationsScenario(
        testInfo.project.name,
        testInfo.file,
        testInfo.title
      )
      const diagnosticCheck = isResetScenario
        ? "password-reset"
        : isAdminNotificationsScenario
          ? "admin-notifications"
          : null
      const pageErrorDiagnostics = createLivePageErrorDiagnostics()
      page.on("pageerror", (error) => {
        errors.push(error)
        if (!diagnosticCheck) return
        let pathname = ""
        try {
          pathname = new URL(page.url()).pathname
        } catch {
          // An unavailable current URL is classified as other, never a new failure.
        }
        pageErrorDiagnostics.record(error, pathname, diagnosticCheck)
      })
      await use(errors)
      if (diagnosticCheck) pageErrorDiagnostics.report(testInfo.project.name, diagnosticCheck)
      expect(errors, errors.map((error) => error.message).join("\n")).toEqual([])
    },
    { auto: true },
  ],
})

export { expect }
