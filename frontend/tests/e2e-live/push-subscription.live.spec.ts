import { randomUUID } from "node:crypto"
import { expect, freshPassword, loginAs, loginWith, stubBreachedPasswordLookup } from "./fixtures"
import { test } from "./native-push-profile-fixtures"
import type { NativePushProfile } from "./native-push-profile-fixtures"
import type { Page } from "@playwright/test"

const expandPushAccordion = async (page: Page): Promise<void> => {
  const accordion = page.getByRole("button", { name: /Push notifications|Push-уведомления/u })
  if ((await accordion.getAttribute("aria-expanded")) !== "true") {
    await accordion.click()
  }
  await expect(accordion).toHaveAttribute("aria-expanded", "true")
}

interface PushSubscriptionResponse {
  id?: unknown
  endpoint?: unknown
}

interface AdminUserRow {
  id: string
  email: string
  full_name: string | null
}

const deleteOnlyCreatedAccount = async (
  adminPage: import("@playwright/test").Page,
  email: string,
  fullName: string
): Promise<void> => {
  const query = new URLSearchParams({ search: fullName, limit: "200" })
  const response = await adminPage.request.get(`/api/v1/users?${query.toString()}`)
  expect(response.status(), "admin can locate the synthetic push-test account").toBe(200)

  const users = (await response.json()) as AdminUserRow[]
  const matches = users.filter((entry) => entry.email === email && entry.full_name === fullName)
  expect(
    matches.length,
    "the generated identity resolves to at most one account"
  ).toBeLessThanOrEqual(1)

  const [match] = matches
  if (!match) return

  const deletion = await adminPage.evaluate(async (userId) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, deleted: false }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const result = await fetch(`/api/v1/users/${encodeURIComponent(userId)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await result.json().catch(() => null)) as { deleted?: boolean } | null
    return { status: result.status, deleted: body?.deleted === true }
  }, match.id)

  expect(deletion.status, "cleanup uses the CSRF-protected admin endpoint").toBe(200)
  expect(deletion.deleted, "cleanup deletes only the exact generated account id").toBe(true)
}

const isPushRoute = (response: { url(): string; request(): { method(): string } }, route: string) =>
  new URL(response.url()).pathname === route && response.request().method() === "POST"

const cleanupOwnedBrowserSubscription = async (
  ownerPage: Page,
  fallbackEndpoint?: string
): Promise<boolean> =>
  ownerPage
    .evaluate(async (knownEndpoint) => {
      const registration = await navigator.serviceWorker.getRegistration()
      const subscription = await registration?.pushManager.getSubscription()
      const endpoint = subscription?.endpoint ?? knownEndpoint
      if (!endpoint) return true

      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) {
        if (subscription) await subscription.unsubscribe()
        return false
      }

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const response = await fetch("/api/v1/push/unsubscribe", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ endpoint }),
      })
      const browserUnsubscribed = subscription ? await subscription.unsubscribe() : true
      return response.ok && browserUnsubscribed
    }, fallbackEndpoint)
    .catch(() => false)

test("Chromium push opt-in persists one native subscription and removes it on opt-out", async ({
  page,
  browser,
  nativePushProfiles,
}, testInfo) => {
  const liveBaseUrl = process.env.LIVE_BASE_URL
  if (!liveBaseUrl) throw new Error("LIVE_BASE_URL must be set by the live acceptance runner")

  const identity = randomUUID()
  const email = `live-push-${testInfo.project.name}-${identity}@university.dev`
  const fullName = `Live Push Acceptance ${testInfo.project.name} ${identity}`
  const password = freshPassword()
  const foreignIdentity = randomUUID()
  const foreignEmail = `live-push-owner-${testInfo.project.name}-${foreignIdentity}@university.dev`
  const foreignFullName = `Live Push Foreign Owner ${testInfo.project.name} ${foreignIdentity}`
  const foreignPassword = freshPassword()
  let registrationAttempted = false
  let ownEndpoint: string | undefined
  let foreignRegistrationAttempted = false
  let foreignSubscriptionMayExist = false
  let foreignEndpoint: string | undefined
  let foreignProfile: NativePushProfile | undefined
  let foreignPage: Page | undefined

  const adminContext = await browser.newContext({
    baseURL: liveBaseUrl,
    ignoreHTTPSErrors: true,
    locale: "ru-RU",
  })
  const adminPage = await adminContext.newPage()

  let subscriptionRequests = 0
  let subscriptionMayExist = false
  page.on("request", (request) => {
    if (
      request.method() === "POST" &&
      new URL(request.url()).pathname === "/api/v1/push/subscribe"
    ) {
      subscriptionRequests += 1
    }
  })

  try {
    const origin = new URL(liveBaseUrl).origin
    // Playwright pre-grants the native permission so Chromium does not block on
    // a non-automatable browser prompt. The source contract separately proves
    // the prompt is reachable only through the explicit settings-switch action.
    await page.context().grantPermissions(["notifications"], { origin })
    foreignProfile = await nativePushProfiles.create()
    const foreignContext = foreignProfile.context
    const secondPage = foreignProfile.page
    foreignPage = secondPage
    await foreignContext.grantPermissions(["notifications"], { origin })

    await loginAs(adminPage, "admin")
    await stubBreachedPasswordLookup(page)
    await page.goto("/register")
    await page.getByLabel("Имя", { exact: true }).fill(fullName)
    await page.getByRole("textbox", { name: "E-mail" }).fill(email)
    await page.getByLabel("Пароль", { exact: true }).fill(password)
    await page.getByLabel("Повторите пароль", { exact: true }).fill(password)
    registrationAttempted = true
    await page.getByRole("button", { name: "Зарегистрироваться" }).click()
    await expect(page).toHaveURL(/\/login$/u)
    await loginWith(page, email, password)

    const profileResponse = await page.request.get("/api/v1/users/me")
    expect(profileResponse.status(), "the synthetic owner can read its own profile").toBe(200)
    const profile = (await profileResponse.json()) as { email?: string }
    expect(profile.email === email).toBe(true)

    await page.goto("/settings?tab=3")
    await expandPushAccordion(page)

    const pushSwitch = page.getByRole("switch", { name: "Включить уведомления" })
    await expect(pushSwitch).toBeVisible()
    await expect(pushSwitch).toBeEnabled()

    const beforeOptIn = await page.evaluate(async () => {
      const supported =
        "serviceWorker" in navigator &&
        "PushManager" in window &&
        typeof Notification !== "undefined"
      if (!supported) return { supported, permission: "unsupported", hasSubscription: false }
      const registration = await navigator.serviceWorker.ready
      return {
        supported,
        permission: Notification.permission,
        hasSubscription: (await registration.pushManager.getSubscription()) !== null,
      }
    })

    expect(beforeOptIn.supported, "Chromium exposes the native push APIs").toBe(true)
    expect(beforeOptIn.permission, "the browser permission is controlled by the test context").toBe(
      "granted"
    )
    expect(beforeOptIn.hasSubscription, "opening settings must not create a push endpoint").toBe(
      false
    )
    expect(subscriptionRequests, "opening settings must not persist a push endpoint").toBe(0)
    await expect(pushSwitch).not.toBeChecked()

    // A second synthetic owner creates a real browser subscription so this
    // account can exercise the server-side foreign-endpoint boundary.
    await stubBreachedPasswordLookup(secondPage)
    await secondPage.goto("/register")
    await secondPage.getByLabel("Имя", { exact: true }).fill(foreignFullName)
    await secondPage.getByRole("textbox", { name: "E-mail" }).fill(foreignEmail)
    await secondPage.getByLabel("Пароль", { exact: true }).fill(foreignPassword)
    await secondPage.getByLabel("Повторите пароль", { exact: true }).fill(foreignPassword)
    foreignRegistrationAttempted = true
    await secondPage.getByRole("button", { name: "Зарегистрироваться" }).click()
    await expect(secondPage).toHaveURL(/\/login$/u)
    await loginWith(secondPage, foreignEmail, foreignPassword)
    const foreignProfileResponse = await secondPage.request.get("/api/v1/users/me")
    expect(
      foreignProfileResponse.status(),
      "the second synthetic owner reads its own profile"
    ).toBe(200)
    const foreignIdentityProfile = (await foreignProfileResponse.json()) as { email?: string }
    expect(foreignIdentityProfile.email === foreignEmail).toBe(true)
    await secondPage.goto("/settings?tab=3")
    await expandPushAccordion(secondPage)

    const foreignPushSwitch = secondPage.getByRole("switch", { name: "Включить уведомления" })
    await expect(foreignPushSwitch).toBeVisible()
    await expect(foreignPushSwitch).not.toBeChecked()
    const foreignBeforeOptIn = await secondPage.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      return (await registration.pushManager.getSubscription()) !== null
    })
    expect(foreignBeforeOptIn, "the second synthetic owner starts without a subscription").toBe(
      false
    )

    const foreignSavePromise = secondPage.waitForResponse((response) =>
      isPushRoute(response, "/api/v1/push/subscribe")
    )
    foreignSubscriptionMayExist = true
    await foreignPushSwitch.click()
    const foreignSave = await foreignSavePromise
    expect(foreignSave.status(), "the second owner persists its own native subscription").toBe(200)
    const foreignRecord = (await foreignSave.json()) as PushSubscriptionResponse
    const foreignRecordId = typeof foreignRecord.id === "string" ? foreignRecord.id : ""
    if (typeof foreignRecord.endpoint !== "string") {
      throw new Error("The foreign owner subscription response did not include its endpoint")
    }
    foreignEndpoint = foreignRecord.endpoint
    const foreignNativeEndpoint = await secondPage.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      return (await registration.pushManager.getSubscription())?.endpoint ?? null
    })
    expect(foreignRecordId.length > 0, "the second owner's record has an identity").toBe(true)
    expect(
      foreignEndpoint === foreignNativeEndpoint,
      "the second server record matches its native browser endpoint"
    ).toBe(true)
    await expect(foreignPushSwitch).toBeChecked()

    const foreignUnsubscribeAttempt = await page.evaluate(async (endpoint) => {
      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return { status: 0, removed: false }

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const response = await fetch("/api/v1/push/unsubscribe", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({ endpoint }),
      })
      const body = (await response.json().catch(() => null)) as { removed?: unknown } | null
      return { status: response.status, removed: body?.removed === true }
    }, foreignEndpoint)
    expect(
      foreignUnsubscribeAttempt.status,
      "the authenticated request receives the normal unsubscribe response"
    ).toBe(200)
    expect(
      foreignUnsubscribeAttempt.removed,
      "authenticated foreign account cannot remove another owner's endpoint"
    ).toBe(false)
    await expect(foreignPushSwitch).toBeChecked()
    await secondPage.reload()
    await expandPushAccordion(secondPage)
    await expect(secondPage.getByRole("switch", { name: "Включить уведомления" })).toBeChecked()
    const foreignSubscriptionAfterReload = await secondPage.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      return (await registration.pushManager.getSubscription()) !== null
    })
    expect(foreignSubscriptionAfterReload, "the second owner's subscription survives reload").toBe(
      true
    )

    const firstSavePromise = page.waitForResponse((response) =>
      isPushRoute(response, "/api/v1/push/subscribe")
    )
    subscriptionMayExist = true
    await pushSwitch.click()
    const firstSave = await firstSavePromise
    expect(firstSave.status(), "explicit opt-in persists the subscription").toBe(200)

    const firstRecord = (await firstSave.json()) as PushSubscriptionResponse
    const firstRecordId = typeof firstRecord.id === "string" ? firstRecord.id : ""
    if (typeof firstRecord.endpoint === "string") ownEndpoint = firstRecord.endpoint
    const nativeSubscription = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()
      return subscription ? subscription.endpoint : null
    })
    expect(firstRecordId.length > 0, "the server returns the persisted subscription identity").toBe(
      true
    )
    expect(
      typeof nativeSubscription === "string" && ownEndpoint === nativeSubscription,
      "the server record belongs to the real browser-generated endpoint"
    ).toBe(true)
    await expect(pushSwitch).toBeChecked()
    expect(subscriptionRequests).toBe(1)

    // Repeat the exact same browser-generated endpoint through the authenticated
    // app route. The endpoint and key material remain in the browser context and
    // are never returned to Node or included in assertion output.
    const duplicateBind = await page.evaluate(async (expectedRecordId) => {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()
      if (!subscription) return { status: 0, endpointMatches: false, sameRecord: false }

      const serialized = subscription.toJSON()
      if (!serialized.keys?.p256dh || !serialized.keys.auth) {
        return { status: 0, endpointMatches: false, sameRecord: false }
      }

      const csrfCookie = document.cookie
        .split(";")
        .map((part) => part.trim())
        .find((part) => part.startsWith("csrf_token="))
      if (!csrfCookie) return { status: 0, endpointMatches: false, sameRecord: false }

      const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
      const response = await fetch("/api/v1/push/subscribe", {
        method: "POST",
        credentials: "same-origin",
        headers: {
          "Content-Type": "application/json",
          "X-CSRF-Token": csrfToken,
        },
        body: JSON.stringify({
          endpoint: subscription.endpoint,
          keys: serialized.keys,
          user_agent: navigator.userAgent,
        }),
      })
      const body = (await response.json().catch(() => null)) as PushSubscriptionResponse | null
      return {
        status: response.status,
        endpointMatches: body?.endpoint === subscription.endpoint,
        sameRecord: body?.id === expectedRecordId,
      }
    }, firstRecordId)

    expect(duplicateBind.status, "rebinding an existing endpoint succeeds").toBe(200)
    expect(
      duplicateBind.endpointMatches,
      "the repeated request uses the same browser endpoint"
    ).toBe(true)
    expect(
      duplicateBind.sameRecord,
      "the repeated endpoint reuses its existing server record"
    ).toBe(true)
    expect(subscriptionRequests, "one duplicate bind reuses the same endpoint record").toBe(2)

    await page.reload()
    await expandPushAccordion(page)
    await expect(page.getByRole("switch", { name: "Включить уведомления" })).toBeChecked()
    const afterReload = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      const subscription = await registration.pushManager.getSubscription()
      return subscription !== null
    })
    expect(afterReload, "the native browser subscription survives a page reload").toBe(true)

    const unsubscribePromise = page.waitForResponse((response) =>
      isPushRoute(response, "/api/v1/push/unsubscribe")
    )
    await page.getByRole("switch", { name: "Включить уведомления" }).click()
    const unsubscribe = await unsubscribePromise
    expect(unsubscribe.status(), "opt-out removes the owned server binding").toBe(200)
    const unsubscribeBody = (await unsubscribe.json()) as { ok?: unknown; removed?: unknown }
    expect(unsubscribeBody.ok === true && unsubscribeBody.removed === true).toBe(true)
    await expect(page.getByRole("switch", { name: "Включить уведомления" })).not.toBeChecked()

    const browserUnsubscribed = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      return (await registration.pushManager.getSubscription()) === null
    })
    expect(browserUnsubscribed, "opt-out also revokes the browser subscription").toBe(true)

    await page.reload()
    await expandPushAccordion(page)
    const pushSwitchAfterOptOut = page.getByRole("switch", { name: "Включить уведомления" })
    await expect(pushSwitchAfterOptOut).toBeEnabled()
    await expect(pushSwitchAfterOptOut).not.toBeChecked()
    const nativeSubscriptionAfterOptOutReload = await page.evaluate(async () => {
      const registration = await navigator.serviceWorker.ready
      return (await registration.pushManager.getSubscription()) !== null
    })
    expect(
      nativeSubscriptionAfterOptOutReload,
      "the native subscription remains absent after reloading the settings page"
    ).toBe(false)

    subscriptionMayExist = false
  } finally {
    try {
      if (subscriptionMayExist) {
        const ownSubscriptionCleaned = await cleanupOwnedBrowserSubscription(page, ownEndpoint)
        expect(
          ownSubscriptionCleaned,
          "a failed acceptance run must remove only its own browser and server subscription"
        ).toBe(true)
      }
    } finally {
      try {
        if (foreignSubscriptionMayExist && foreignPage) {
          const foreignSubscriptionCleaned = await cleanupOwnedBrowserSubscription(
            foreignPage,
            foreignEndpoint
          )
          expect(
            foreignSubscriptionCleaned,
            "cleanup removes only the second synthetic owner's browser and server subscription"
          ).toBe(true)
        }
      } finally {
        try {
          if (foreignRegistrationAttempted) {
            await deleteOnlyCreatedAccount(adminPage, foreignEmail, foreignFullName)
          }
        } finally {
          try {
            if (registrationAttempted) await deleteOnlyCreatedAccount(adminPage, email, fullName)
          } finally {
            await adminContext.close()
          }
        }
      }
    }
  }
})
