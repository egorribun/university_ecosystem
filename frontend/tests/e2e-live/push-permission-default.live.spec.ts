import { expect, loginAs, test } from "./fixtures"

test("Chromium leaves notification permission at default when settings are only opened", async ({
  page,
  browserName,
}) => {
  test.skip(
    browserName !== "chromium",
    "native Notifications and PushManager are Chromium acceptance"
  )

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

  const beforeSettings = await page.evaluate(async () => {
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

  expect(beforeSettings.supported, "Chromium exposes the native push APIs").toBe(true)
  expect(beforeSettings.permission, "the fresh context has no notification grant").toBe("default")
  expect(beforeSettings.hasSubscription, "the test starts without a browser endpoint").toBe(false)

  await page.goto("/settings?tab=3")
  const pushSwitch = page.getByRole("switch", {
    name: /Включить уведомления|Enable notifications/u,
  })
  await expect(pushSwitch).toBeVisible()
  await expect(pushSwitch).toBeEnabled()
  await expect(pushSwitch).not.toBeChecked()

  const afterSettings = await page.evaluate(async () => {
    const registration = await navigator.serviceWorker.ready
    const subscription = await registration.pushManager.getSubscription()
    return {
      permission: Notification.permission,
      hasSubscription: subscription !== null,
    }
  })

  expect(afterSettings.permission, "opening settings must not request permission").toBe("default")
  expect(afterSettings.hasSubscription, "opening settings must not create a browser endpoint").toBe(
    false
  )
  expect(subscriptionRequests, "opening settings must not create a server binding").toBe(0)
})
