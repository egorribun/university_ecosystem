import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

for (const viewport of [
  { width: 360, height: 640 },
  { width: 1440, height: 900 },
]) {
  test(`contextual push offer stays inside ${viewport.width}x${viewport.height}`, async ({
    page,
  }) => {
    await page.setViewportSize(viewport)
    // Headless Chromium denies notifications by default. Keep this test in
    // the supported, undecided state without actually requesting permission.
    await page.addInitScript(() => {
      Object.defineProperty(Notification, "permission", {
        configurable: true,
        value: "default",
      })
      const query = navigator.permissions.query.bind(navigator.permissions)
      Object.defineProperty(navigator.permissions, "query", {
        configurable: true,
        value: (descriptor: PermissionDescriptor) =>
          descriptor.name === "notifications"
            ? Promise.resolve({
                name: "notifications",
                state: "prompt",
                onchange: null,
                addEventListener() {},
                removeEventListener() {},
                dispatchEvent: () => true,
              } satisfies PermissionStatus)
            : query(descriptor),
      })
    })
    const { login } = await useMockApi(page)
    await login(page)

    const startsAt = new Date(Date.now() + 24 * 60 * 60 * 1_000)
    const endsAt = new Date(startsAt.getTime() + 2 * 60 * 60 * 1_000)
    await page.route("**/api/v1/events/uuid-10**", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "uuid-10",
          title: "Contextual Push Test Event",
          description: "Registration opens the push education offer",
          location: "Main Hall",
          event_type: "lecture",
          starts_at: startsAt.toISOString(),
          ends_at: endsAt.toISOString(),
          created_at: new Date().toISOString(),
          created_by: "uuid-1",
          is_active: true,
          participant_count: 0,
          is_registered: false,
          files: [],
        }),
      })
    )
    await page.route("**/api/v1/events/attendance", (route) =>
      route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          id: "00000000-0000-4000-8000-000000000011",
          user_id: "00000000-0000-4000-8000-000000000001",
          event_id: "00000000-0000-4000-8000-000000000010",
          registered_at: new Date().toISOString(),
          qr_token: "contextual-push-qr",
        }),
      })
    )
    await page.goto("/events/uuid-10", { waitUntil: "commit" })

    const pushSupport = await page.evaluate(() => ({
      serviceWorker: "serviceWorker" in navigator,
      pushManager: "PushManager" in window,
      notification: typeof Notification !== "undefined",
      permission: typeof Notification === "undefined" ? null : Notification.permission,
    }))
    expect(pushSupport).toEqual({
      serviceWorker: true,
      pushManager: true,
      notification: true,
      permission: "default",
    })

    const panel = page.locator(".fixed.z-toast.pointer-events-none").filter({
      has: page.getByRole("heading", { name: /notifications|уведомления/i }),
    })
    await expect(panel).toHaveCount(0)

    await page.getByRole("button", { name: /register|записаться|зарегистрироваться/i }).click()
    await expect(panel).toHaveCount(1)

    const box = await panel.boundingBox()
    expect(box).not.toBeNull()
    expect(box!.x).toBeGreaterThanOrEqual(0)
    expect(box!.y).toBeGreaterThanOrEqual(0)
    expect(box!.x + box!.width).toBeLessThanOrEqual(viewport.width)
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport.height)
  })
}
