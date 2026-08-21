import { expect, test, type Page } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const TEST_TIMEOUTS = {
  short: 5000,
  medium: 10000,
  long: 15000,
  extended: 25000,
}

const trackHydrationErrors = (page: Page): string[] => {
  const errors: string[] = []
  const capture = (message: string) => {
    if (/Hydration failed|hydration mismatch|Minified React error #418/i.test(message)) {
      errors.push(message)
    }
  }
  page.on("console", (message) => {
    if (message.type() === "error") capture(message.text())
  })
  page.on("pageerror", (error) => capture(error.message))
  return errors
}

test.describe("University ecosystem app", () => {
  test("allows a student to login and reach the dashboard", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await expect(page.getByText(/Иван|Ivan/i)).toBeVisible({ timeout: TEST_TIMEOUTS.extended })
    const newsLink = page.getByRole("link", { name: /Новости|News/i }).first()
    await expect(newsLink).toBeVisible({ timeout: TEST_TIMEOUTS.extended })
  })

  test("supports navigation between main sections", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await page
      .getByRole("link", { name: /Посмотреть все|See all/i })
      .first()
      .click()
    await expect(page).toHaveURL(/\/news$/)
    await expect(page.getByRole("heading", { name: /Новости|News/i })).toBeVisible()

    await page
      .getByRole("link", { name: /На главную|На главну|Home/i })
      .first()
      .click()
    await expect(page).toHaveURL(/\/dashboard$/)

    await page.getByRole("link", { name: /Полное расписание|Full schedule/i }).click()
    await expect(page).toHaveURL(/\/schedule$/)
    await expect(page.getByText(/Расписание|Schedule/i).first()).toBeVisible()
  })

  test("caches news responses using ETag", async ({ page }) => {
    const hydrationErrors = trackHydrationErrors(page)

    const mock = await useMockApi(page)
    await mock.login(page)

    await page
      .getByRole("link", { name: /Посмотреть все|See all/i })
      .first()
      .click()
    await expect(page.getByText(/Новость дня|News of the day/i)).toBeVisible()

    // Wait for the cache effect to run and verify it's saved
    await expect(async () => {
      const cached = await page.evaluate(
        () => localStorage.getItem("news:list:ru") || localStorage.getItem("news:list:en")
      )
      if (!cached) throw new Error("news:list cache not found in localStorage")
      const parsed = JSON.parse(cached)
      if (!Array.isArray(parsed) || parsed.length === 0)
        throw new Error("news:list is empty or invalid")
    }).toPass({ timeout: TEST_TIMEOUTS.medium })

    // The production cache deliberately batches localStorage writes and
    // flushes them when a tab becomes hidden. Reproduce that lifecycle edge
    // synchronously before creating a fresh document.
    await page.evaluate(() => {
      Object.defineProperty(document, "visibilityState", {
        configurable: true,
        value: "hidden",
      })
      document.dispatchEvent(new Event("visibilitychange"))
    })
    await page.reload({ waitUntil: "networkidle" })
    await expect(page.getByText(/Новость дня|News of the day/i)).toBeVisible()

    expect(mock.state.newsLog.some((entry) => entry.status === 304)).toBeTruthy()
    expect(mock.state.newsLog.filter((entry) => entry.status === 200).length).toBeGreaterThan(0)
    expect(hydrationErrors).toEqual([])
  })

  test("reuses cached news data when the API is offline", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    // 1. Visit news page to populate localStorage
    await page
      .getByRole("link", { name: /Посмотреть все|See all/i })
      .first()
      .click()
    await expect(
      page.getByText(/\u041d\u043e\u0432\u043e\u0441\u0442\u044c \u0434\u043d\u044f/)
    ).toBeVisible()

    // 2. Wait for localStorage to be populated
    await expect(async () => {
      const cached = await page.evaluate(() => localStorage.getItem("news:list:ru"))
      if (!cached) throw new Error("news:list:ru not found")
    }).toPass({ timeout: TEST_TIMEOUTS.short })

    // Keep the document server and auth endpoints available while making only
    // the news API unavailable. A fresh document must hydrate from the cache,
    // not from TanStack Query's previous in-memory result.
    await mock.setNewsOffline(true)
    try {
      await page.reload({ waitUntil: "domcontentloaded" })
      await expect(page.getByText(/Новость дня|News of the day/i)).toBeVisible({
        timeout: TEST_TIMEOUTS.long,
      })
    } finally {
      await mock.setNewsOffline(false)
    }
  })

  test("allows revoking secondary sessions from settings", async ({ page }) => {
    const hydrationErrors = trackHydrationErrors(page)
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings")
    await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()

    await page.getByRole("tab", { name: /Security|Безопасность/i }).click()

    // Verify sessions list
    const sessionsAccordion = page.getByRole("button", {
      name: /Устройства и сессии|Devices (?:&|and) sessions/i,
    })
    await expect(sessionsAccordion).toBeVisible()
    await sessionsAccordion.click()
    await expect(page.getByText("Safari/17.0")).toBeVisible()

    const revokeButton = page.getByRole("button", { name: /^Завершить$|^Revoke$/i })
    await expect(revokeButton).toBeVisible()
    await expect(revokeButton).toBeEnabled()

    // Set up response listener first
    const responsePromise = page.waitForResponse(
      (resp) => resp.url().includes("/auth/sessions/") && resp.request().method() === "DELETE",
      { timeout: TEST_TIMEOUTS.extended }
    )

    // Use standard click which handles scrolling and visibility checks
    await revokeButton.click()

    const response = await responsePromise
    expect(response.ok()).toBeTruthy()

    // 1. Wait for success toast
    await expect(page.getByText(/Сессия завершена|Session ended/i).first()).toBeVisible({
      timeout: TEST_TIMEOUTS.long,
    })

    // 2. Reload to ensure persistence
    await page.reload()
    await page.getByRole("tab", { name: /Security|Безопасность/i }).click()
    await page
      .getByRole("button", { name: /Устройства и сессии|Devices (?:&|and) sessions/i })
      .click()

    // 3. Verify the revoked state persists and the action is no longer offered.
    await expect(page.getByText(/^Завершена$|^Revoked$/i).first()).toBeVisible({
      timeout: TEST_TIMEOUTS.long,
    })
    await expect(page.getByRole("button", { name: /^Завершить$|^Revoke$/i })).toBeHidden()
    expect(hydrationErrors).toEqual([])
  })

  test("allows loading additional events from the events page", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    // The sentinel can be inside the viewport as soon as the SSR-hydrated
    // first page mounts. Arm the listener before navigation so an eager
    // IntersectionObserver fetch cannot race past the assertion.
    const nextEventsResponse = page.waitForResponse(
      (response) => {
        const url = new URL(response.url())
        return (
          response.request().method() === "GET" &&
          // The production client may target `http://api/v1/events` in the
          // preview harness, while the browser-gateway path is `/api/v1/events`.
          // Both represent the same endpoint; match the stable `/v1/events`
          // suffix so the assertion is origin-independent.
          url.pathname.endsWith("/v1/events") &&
          url.searchParams.has("cursor")
        )
      },
      { timeout: TEST_TIMEOUTS.extended }
    )

    // The initial page is SSR-prefetched, so its request may complete on the
    // server before the browser can observe it. Assert hydrated content rather
    // than waiting for a client-side response that is intentionally absent.
    await page.goto("/events")
    await page.waitForURL(/\/events$/)

    await expect(page.getByText(/(?:Событие|Event) uuid-10/i).first()).toBeVisible({
      timeout: TEST_TIMEOUTS.long,
    })

    // The current feed uses an IntersectionObserver sentinel instead of a
    // manual "load more" button. Reaching the last card on page one must
    // fetch the next cursor page.
    await page.getByTestId("events-next-page-sentinel").scrollIntoViewIfNeeded()
    await nextEventsResponse
    await expect(page.getByText(/(?:Событие|Event) uuid-25/i).first()).toBeVisible()
  })

  test("persists theme preference across reloads", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/settings", { waitUntil: "networkidle" })
    await expect(page.getByRole("heading", { name: /Settings|Настройки/i })).toBeVisible()

    await page.evaluate(() => {
      localStorage.setItem("ue-mode", "dark")
    })

    await page.reload()
    await expect(page.locator("html")).toHaveClass(/dark/)
  })

  test("allows updating user profile settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/profile?edit=1", { waitUntil: "networkidle" })

    const saveBtn = page.getByRole("button", { name: /Сохранить|Save/i })
    await expect(saveBtn).toBeVisible()

    const aboutInput = page.getByRole("textbox", { name: /О себе|About/i })
    const newBio = `Updated bio ${Date.now()}`
    await aboutInput.fill(newBio)
    await saveBtn.click()

    await expect(page.getByText(newBio)).toBeVisible()
    await page.reload()
    await expect(page.getByText(newBio)).toBeVisible()
  })
})
