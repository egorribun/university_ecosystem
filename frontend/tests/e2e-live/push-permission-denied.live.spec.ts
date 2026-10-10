import type { BrowserContext, Page } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"

const expandPushAccordion = async (page: Page): Promise<void> => {
  const accordion = page.getByRole("button", { name: /Push notifications|Push-уведомления/u })
  if ((await accordion.getAttribute("aria-expanded")) !== "true") {
    await accordion.click()
  }
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
}

const readNativePushState = async (page: Page) =>
  page.evaluate(async () => {
    const supported =
      "serviceWorker" in navigator && "PushManager" in window && typeof Notification !== "undefined"
    if (!supported) {
      return { supported, permission: "unsupported", hasSubscription: false }
    }

    const registration = await navigator.serviceWorker.ready
    return {
      supported,
      permission: Notification.permission,
      hasSubscription: (await registration.pushManager.getSubscription()) !== null,
    }
  })

const expectDeniedSettings = async (page: Page): Promise<void> => {
  const state = await readNativePushState(page)
  expect(state.supported, "Chromium exposes native notification and push APIs").toBe(true)
  expect(state.permission, "the isolated context remains denied").toBe("denied")
  expect(state.hasSubscription, "denied permission must not create a browser subscription").toBe(
    false
  )
  await expandPushAccordion(page)
  await expect(
    page.getByText(/Текущее состояние:\s*запрещено|Current status:\s*blocked/u)
  ).toBeVisible()
  await expect(
    page.getByRole("switch", { name: /Включить уведомления|Turn on notifications/u })
  ).toHaveCount(0)
}

test("Chromium shows the denied notification permission without creating a subscription", async ({
  browser,
  browserName,
}) => {
  test.skip(
    browserName !== "chromium",
    "native Notifications and PushManager permission acceptance is Chromium-only"
  )

  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")
  const origin = new URL(liveBaseUrl).origin
  const browserSession = await browser.newBrowserCDPSession()
  let isolatedContext: BrowserContext | undefined

  try {
    const contextsBefore = new Set(
      (await browserSession.send("Target.getBrowserContexts")).browserContextIds
    )
    isolatedContext = await browser.newContext({
      baseURL: liveBaseUrl,
      ignoreHTTPSErrors: true,
      locale: "ru-RU",
    })
    const contextsAfter = (await browserSession.send("Target.getBrowserContexts")).browserContextIds
    const createdContextIds = contextsAfter.filter((id) => !contextsBefore.has(id))
    expect(
      createdContextIds,
      "the permission override is scoped to this test context"
    ).toHaveLength(1)
    const browserContextId = createdContextIds[0]
    if (!browserContextId) throw new Error("Chromium did not expose the isolated browser context")

    await browserSession.send("Browser.setPermission", {
      browserContextId,
      origin,
      permission: { name: "notifications" },
      setting: "denied",
    })

    const page = await isolatedContext.newPage()
    let subscriptionRequests = 0
    page.on("request", (request) => {
      if (
        request.method() === "POST" &&
        new URL(request.url()).pathname === "/api/v1/push/subscribe"
      ) {
        subscriptionRequests += 1
      }
    })

    await loginAs(page, "student")
    await page.goto("/settings?tab=3")
    await expectDeniedSettings(page)
    expect(subscriptionRequests, "viewing denied settings must not persist a subscription").toBe(0)

    await page.reload()
    await expectDeniedSettings(page)
    expect(subscriptionRequests, "reload must not persist a subscription").toBe(0)
  } finally {
    try {
      await isolatedContext?.close()
    } finally {
      await browserSession.detach()
    }
  }
})
