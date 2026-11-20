import type { Page } from "@playwright/test"

// Playwright serializes this function into the page; keep it self-contained.
export function setCsrfClickExpiry(enabled: boolean): void {
  const key = Symbol.for("university.live-profile-csrf.expiry")
  const previous: unknown = Reflect.get(document, key)
  if (previous instanceof AbortController) previous.abort()
  Reflect.deleteProperty(document, key)
  if (!enabled) return

  const controller = new AbortController()
  document.addEventListener(
    "click",
    (event) => {
      if (!event.isTrusted) return
      controller.abort()
      Reflect.deleteProperty(document, key)
      const secureAttribute = location.protocol === "https:" ? "; Secure" : ""
      document.cookie = `csrf_token=; Max-Age=0; Path=/; SameSite=Lax${secureAttribute}`
    },
    { capture: true, signal: controller.signal }
  )
  Reflect.set(document, key, controller)
}

export async function clickWithExpiredCsrf(page: Page, click: () => Promise<void>): Promise<void> {
  await page.evaluate(setCsrfClickExpiry, true)
  const [action] = await Promise.allSettled([Promise.resolve().then(click)])
  const [cleanup] = await Promise.allSettled([
    Promise.resolve().then(async () => {
      if (!page.isClosed()) await page.evaluate(setCsrfClickExpiry, false)
    }),
  ])
  if (action.status === "rejected") throw action.reason
  if (cleanup.status === "rejected") throw cleanup.reason
}
