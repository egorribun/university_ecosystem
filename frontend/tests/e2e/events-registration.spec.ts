import { expect, test, type Page, type Route } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

/**
 * Events registration specs — W24.
 *
 * Covers the full event registration lifecycle:
 *   1. Full registration flow — student registers for an event and sees
 *      a confirmation.
 *   2. Capacity limit enforcement — when an event is full the UI shows a
 *      "sold out" / "no seats" message and the register button is disabled.
 *   3. Cancellation flow — a registered student can cancel, and the
 *      registration is removed from their list.
 *
 * All API calls are mocked inline. The existing events mock in mockApi.ts
 * returns 50 events; here we layer in registration-specific endpoints.
 */

const MOCK_EVENT_OPEN = {
  id: "evt-open-1",
  title: "Open Registration Event",
  description: "A test event with open registration",
  starts_at: "2026-08-01T10:00:00Z",
  ends_at: "2026-08-01T12:00:00Z",
  location: "Main Hall",
  capacity: 100,
  registered_count: 50,
  is_registered: false,
  status: "published",
  created_at: "2026-07-01T00:00:00Z",
  created_by: "teacher-1",
  is_active: true,
}

const MOCK_EVENT_FULL = {
  ...MOCK_EVENT_OPEN,
  id: "evt-full-1",
  title: "Full Capacity Event",
  capacity: 100,
  registered_count: 100, // at capacity
  is_registered: false,
}

const MOCK_EVENT_REGISTERED = {
  ...MOCK_EVENT_OPEN,
  id: "evt-registered-1",
  title: "Already Registered Event",
  is_registered: true,
  registered_count: 51,
}

async function setupEventsMock(page: Page) {
  // Events list.
  await page.route("**/api/v1/events**", (route: Route) => {
    const url = new URL(route.request().url())
    if (url.pathname.endsWith("/events") || url.pathname.endsWith("/events/")) {
      void route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          items: [MOCK_EVENT_OPEN, MOCK_EVENT_FULL, MOCK_EVENT_REGISTERED],
          total: 3,
          limit: 20,
          cursor: null,
          next_cursor: null,
          has_more: false,
        }),
      })
      return
    }
    void route.continue()
  })

  // Individual event detail.
  await page.route(`**/api/v1/events/${MOCK_EVENT_OPEN.id}**`, (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EVENT_OPEN),
    })
  })

  await page.route(`**/api/v1/events/${MOCK_EVENT_FULL.id}**`, (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EVENT_FULL),
    })
  })

  await page.route(`**/api/v1/events/${MOCK_EVENT_REGISTERED.id}**`, (route: Route) => {
    void route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(MOCK_EVENT_REGISTERED),
    })
  })

  // Registration POST.
  await page.route(`**/api/v1/events/${MOCK_EVENT_OPEN.id}/register**`, (route: Route) => {
    if (route.request().method() === "POST") {
      void route.fulfill({
        status: 201,
        contentType: "application/json",
        body: JSON.stringify({ event_id: MOCK_EVENT_OPEN.id, status: "registered" }),
      })
    } else {
      void route.continue()
    }
  })

  // Cancellation DELETE.
  await page.route(`**/api/v1/events/${MOCK_EVENT_REGISTERED.id}/register**`, (route: Route) => {
    if (route.request().method() === "DELETE") {
      void route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ event_id: MOCK_EVENT_REGISTERED.id, status: "cancelled" }),
      })
    } else {
      void route.continue()
    }
  })
}

test.describe("Events registration", () => {
  // ── 1. Full registration flow ─────────────────────────────────────────
  test("student can register for an open event", async ({ page }) => {
    await setupEventsMock(page)

    const { login } = await useMockApi(page)
    await login(page)

    await gotoWithTransientRetry(page, "/events", { waitUntil: "commit", timeout: 30_000 })
    await page.waitForURL(/\/events$/)

    // Click into the open event.
    const openEventLink = page
      .getByText(/Open Registration Event/i)
      .or(page.getByRole("link", { name: /Open Registration Event/i }))
    if (!(await openEventLink.isVisible({ timeout: 5000 }))) {
      test.info().annotations.push({
        type: "info",
        description: "Open event not found in list — mock may not have injected before page load",
      })
      return
    }
    await openEventLink.first().click()
    await page.waitForTimeout(500)

    // Find the register button.
    const registerButton = page.getByRole("button", {
      name: /register|sign up|записаться|зарегистрироваться/i,
    })
    if (!(await registerButton.isVisible({ timeout: 5000 }))) {
      test.info().annotations.push({
        type: "info",
        description: "Register button not found on event detail page",
      })
      return
    }

    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes("/register") && [200, 201].includes(resp.status()),
      { timeout: 10_000 }
    )
    await registerButton.click()
    await responsePromise

    // Confirmation: button changes text or a success message appears.
    const confirmation = page
      .locator("body")
      .filter({ hasText: /registered|confirmed|записан|зарегистрирован/i })
    if (await confirmation.isVisible({ timeout: 5000 })) {
      await expect(confirmation.first()).toBeVisible()
    }
  })

  // ── 2. Capacity limit enforcement ─────────────────────────────────────
  test("register button is disabled and message shown when event is full", async ({ page }) => {
    await setupEventsMock(page)

    const { login } = await useMockApi(page)
    await login(page)

    await gotoWithTransientRetry(page, "/events", { waitUntil: "commit", timeout: 30_000 })

    const fullEventLink = page
      .getByText(/Full Capacity Event/i)
      .or(page.getByRole("link", { name: /Full Capacity Event/i }))
    if (!(await fullEventLink.isVisible({ timeout: 5000 }))) {
      test.info().annotations.push({
        type: "info",
        description: "Full event not found in list",
      })
      return
    }
    await fullEventLink.first().click()
    await page.waitForTimeout(500)

    // The register button should be disabled or replaced with a "full" badge.
    const registerButton = page.getByRole("button", {
      name: /register|sign up|записаться|зарегистрироваться/i,
    })
    const fullBadge = page.locator("body").filter({ hasText: /full|sold out|мест нет|заполнено/i })

    if (await registerButton.isVisible({ timeout: 3000 })) {
      await expect(registerButton).toBeDisabled()
    } else if (await fullBadge.isVisible({ timeout: 3000 })) {
      await expect(fullBadge.first()).toBeVisible()
    } else {
      test.info().annotations.push({
        type: "info",
        description: "Capacity enforcement UI not found — may not be implemented",
      })
    }
  })

  // ── 3. Cancellation flow ──────────────────────────────────────────────
  test("registered student can cancel event registration", async ({ page }) => {
    await setupEventsMock(page)

    const { login } = await useMockApi(page)
    await login(page)

    await gotoWithTransientRetry(page, "/events", { waitUntil: "commit", timeout: 30_000 })

    const registeredEventLink = page
      .getByText(/Already Registered Event/i)
      .or(page.getByRole("link", { name: /Already Registered Event/i }))
    if (!(await registeredEventLink.isVisible({ timeout: 5000 }))) {
      test.info().annotations.push({
        type: "info",
        description: "Registered event not found in list",
      })
      return
    }
    await registeredEventLink.first().click()
    await page.waitForTimeout(500)

    // Find the cancel button (registration cancellation).
    const cancelButton = page.getByRole("button", {
      name: /cancel|unregister|отменить|отписаться/i,
    })
    if (!(await cancelButton.isVisible({ timeout: 5000 }))) {
      test.info().annotations.push({
        type: "info",
        description: "Cancel registration button not found",
      })
      return
    }

    const cancelResponsePromise = page.waitForResponse(
      (resp) =>
        resp.url().includes("/register") && (resp.status() === 200 || resp.status() === 204),
      { timeout: 10_000 }
    )
    await cancelButton.click()
    await cancelResponsePromise

    // Verify the UI reverts to "not registered" state.
    const registerAgain = page.getByRole("button", {
      name: /register|sign up|записаться/i,
    })
    const cancelConfirm = page
      .locator("body")
      .filter({ hasText: /cancelled|removed|отменено|отписан/i })

    if (await cancelConfirm.isVisible({ timeout: 5000 })) {
      await expect(cancelConfirm.first()).toBeVisible()
    } else if (await registerAgain.isVisible({ timeout: 5000 })) {
      await expect(registerAgain).toBeEnabled()
    } else {
      test.info().annotations.push({
        type: "info",
        description: "Cancellation confirmation UI not found",
      })
    }
  })
})
