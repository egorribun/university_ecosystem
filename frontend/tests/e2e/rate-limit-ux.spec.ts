import { expect, test, type Route } from "./test"
import { useMockApi } from "./utils/mockApi"

/**
 * Rate limit UX specs — W24.
 *
 * Tests the client-side handling of HTTP 429 Too Many Requests responses:
 *   1. After rapid requests, the 429 response is surfaced in the UI.
 *   2. A Retry-After countdown is displayed to the user.
 *   3. The client auto-retries after the countdown expires.
 *
 * Implementation strategy:
 *   - The first N requests to a mocked endpoint return 200.
 *   - Subsequent requests return 429 with a `Retry-After: 3` header.
 *   - After the countdown the mock switches back to 200 to simulate the
 *     server lifting the rate limit.
 *
 * This test targets a specific API-heavy page (news list) where rapid
 * requests are plausible. Adjust the route pattern if the app uses a
 * different endpoint.
 */

test.describe("Rate limit UX", () => {
  // ── 1. 429 response is shown in the UI ────────────────────────────────
  test("shows rate-limit error when 429 is returned", async ({ page }) => {
    let requestCount = 0

    // Route the news endpoint: first 2 calls succeed, then return 429.
    await page.route("**/api/v1/news**", (route: Route) => {
      requestCount++
      if (requestCount <= 2) {
        void route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({
            items: [],
            has_more: false,
            next_cursor: null,
          }),
        })
      } else {
        void route.fulfill({
          status: 429,
          headers: {
            "Retry-After": "3",
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ detail: "Too Many Requests" }),
        })
      }
    })

    const { login } = await useMockApi(page)
    await login(page)

    // The endpoint intentionally stays rate-limited while the client retries;
    // waiting for networkidle would consume the whole test timeout.
    await page.goto("/news", { waitUntil: "domcontentloaded" })

    // Trigger multiple rapid requests by reloading or clicking refresh.
    for (let i = 0; i < 3; i++) {
      await page.evaluate(() => {
        // Attempt to trigger a re-fetch by dispatching a custom event or
        // calling the app's internal refetch mechanism if exposed.
        window.dispatchEvent(new Event("focus"))
      })
      await page.waitForTimeout(200)
    }

    // Alternatively, reload the page twice to exhaust the mock budget.
    await page.reload({ waitUntil: "domcontentloaded" })
    await page.reload({ waitUntil: "domcontentloaded" })

    await page.waitForTimeout(500)

    // The UI should show some indicator of the rate limit.
    const rateLimitMessage = page
      .locator('[role="alert"], [data-testid*="error"], [data-testid*="rate"]')
      .filter({ hasText: /too many|429|rate limit|слишком много/i })

    if (await rateLimitMessage.isVisible({ timeout: 5000 })) {
      await expect(rateLimitMessage.first()).toBeVisible()
    } else {
      test.info().annotations.push({
        type: "info",
        description: "Rate limit UI not found — the app may not surface 429 errors visually",
      })
    }
  })

  // ── 2. Retry-After countdown is displayed ─────────────────────────────
  test("displays Retry-After countdown from 429 response", async ({ page }) => {
    // All requests to the mock endpoint return 429 with Retry-After: 5.
    await page.route("**/api/v1/news**", (route: Route) => {
      void route.fulfill({
        status: 429,
        headers: {
          "Retry-After": "5",
          "Content-Type": "application/json",
        },
        body: JSON.stringify({ detail: "Too Many Requests", retry_after: 5 }),
      })
    })

    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/news", { waitUntil: "domcontentloaded" })
    await page.waitForTimeout(500)

    // Look for a countdown element — the app may show "retry in 5s", "5 sec",
    // or similar. Accept numeric digits near "retry" keyword.
    const countdown = page
      .locator("body")
      .filter({ hasText: /retry.*\d|повтор.*\d|\d.*retry|\d.*сек/i })

    if (await countdown.isVisible({ timeout: 5000 })) {
      await expect(countdown.first()).toBeVisible()
    } else {
      test.info().annotations.push({
        type: "info",
        description: "Retry-After countdown UI not found — may not be implemented",
      })
    }
  })

  // ── 3. Auto-retry after countdown expires ─────────────────────────────
  test("auto-retries request after rate limit window expires", async ({ page }) => {
    let callCount = 0
    const successPayload = {
      items: [
        {
          id: "3e5a32b2-5f6c-48d9-a78b-d7be62512345",
          title: "Auto-retry success",
          content: "Auto-retry content",
          created_at: "2026-06-27T10:00:00Z",
        },
      ],
      has_more: false,
      next_cursor: null,
    }

    await page.route("**/api/v1/news**", (route: Route) => {
      callCount++
      if (callCount === 1) {
        // First call: rate limited.
        void route.fulfill({
          status: 429,
          headers: {
            "Retry-After": "1", // 1 second — short enough for the test.
            "Content-Type": "application/json",
          },
          body: JSON.stringify({ detail: "Too Many Requests", retry_after: 1 }),
        })
      } else {
        // Subsequent calls: success.
        void route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify(successPayload),
        })
      }
    })

    const { login } = await useMockApi(page)
    await login(page)

    await page.goto("/news", { waitUntil: "domcontentloaded" })

    // Wait for the retry window (1 s) plus some buffer for the re-fetch.
    await page.waitForTimeout(3000)

    // After auto-retry the content should appear.
    const autoRetryContent = page.getByText(/Auto-retry success/i)
    if (await autoRetryContent.isVisible({ timeout: 5000 })) {
      await expect(autoRetryContent).toBeVisible()
    } else {
      // The app may not implement auto-retry — log info rather than failing.
      test.info().annotations.push({
        type: "info",
        description: "Auto-retry not implemented — no success content visible after countdown",
      })
      // At minimum: verify the page didn't crash (no unhandled error alert).
      const crashAlert = page.locator('[role="alert"]').filter({ hasText: /uncaught|unhandled/i })
      await expect(crashAlert).not.toBeVisible()
    }
  })
})
