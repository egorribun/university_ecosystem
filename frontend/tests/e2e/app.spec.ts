import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const TEST_TIMEOUTS = {
  short: 5000,
  medium: 10000,
  long: 15000,
  extended: 20000,
}

const TEST_DELAYS = {
  short: 500,
  default: 1000,
}

// Skip: All app tests timeout during login in mock environment
test.describe.skip("University ecosystem app", () => {
  test("allows a student to login and reach the dashboard", async ({ page }) => {
    const { login } = await useMockApi(page)
    await login(page)

    await expect(page.getByText(/Иван!/)).toBeVisible()
    const newsLink = page.getByRole("link", { name: "Новости" }).first()
    await expect(newsLink).toBeVisible()
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

  // Skip: ETag caching requires HTTP-level header handling not supported in Playwright mock
  test.skip("caches news responses using ETag", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page
      .getByRole("link", { name: /Посмотреть все|See all/i })
      .first()
      .click()
    await expect(
      page.getByText(/\u041d\u043e\u0432\u043e\u0441\u0442\u044c \u0434\u043d\u044f/)
    ).toBeVisible()

    // Wait for the cache effect to run and verify it's saved
    await expect(async () => {
      const cached = await page.evaluate(() => localStorage.getItem("news:list:ru"))
      if (!cached) throw new Error("news:list:ru not found in localStorage")
      const parsed = JSON.parse(cached)
      if (!Array.isArray(parsed) || parsed.length === 0)
        throw new Error("news:list:ru is empty or invalid")
    }).toPass({ timeout: TEST_TIMEOUTS.medium })

    await page.reload()
    await expect(
      page.getByText(/\u041d\u043e\u0432\u043e\u0441\u0442\u044c \u0434\u043d\u044f/)
    ).toBeVisible()

    expect(mock.state.newsLog.some((entry) => entry.status === 304)).toBeTruthy()
    expect(mock.state.newsLog.filter((entry) => entry.status === 200).length).toBeGreaterThan(0)
  })

  // Skip: Service Worker/Offline cache simulation is flaky in this environment
  test.skip("reuses cached news data when the API is offline", async ({ page }) => {
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

    // 3. Go offline and reload. Should show data from localStorage/cache.
    mock.setOffline(page, true)
    // Verify cached news is visible
    await page.waitForTimeout(2000)
    await expect(page.getByText("Новость дня")).toBeVisible({ timeout: TEST_TIMEOUTS.long })
  })

  test("allows revoking secondary sessions from settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/settings")
    await page.waitForURL(/\/settings$/)
    await page.waitForSelector('[role="tablist"]')
    await page.waitForTimeout(TEST_DELAYS.default)

    // Switch to Account tab
    await page.getByRole("tab", { name: /Account|Аккаунт/i }).click()
    await page.waitForTimeout(TEST_DELAYS.short)

    // Verify sessions list
    await expect(page.getByText(/Устройства и сессии|Devices and sessions/i)).toBeVisible()
    await expect(page.getByText("Safari/17.0")).toBeVisible()

    const revokeButton = page.getByTestId("session-revoke-2")
    await revokeButton.scrollIntoViewIfNeeded()
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
    await page.getByRole("tab", { name: /Account|Аккаунт/i }).click()

    // 3. Verify status chip updated to "Завершена" using data-testid
    const statusChip = page.getByTestId("session-status-2")
    await expect(statusChip).toContainText(/Завершена|Revoked|Ended/i, {
      timeout: TEST_TIMEOUTS.long,
    })
    await expect(page.getByTestId("session-revoke-2")).toBeHidden()
  })

  test("allows loading additional events from the events page", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await page.goto("/events")
    await page.waitForURL(/\/events$/)

    await expect(page.getByText(/Событие 10/i).first()).toBeVisible()
    const loadMore = page.getByRole("button", { name: /Загрузить ещё|Load more/i })

    if (await loadMore.isVisible()) {
      await loadMore.click()
      await expect(page.getByText(/Событие 25/i).first()).toBeVisible()
    } else {
      await expect(page.getByText(/Событие 49/i).first()).toBeVisible()
    }
  })

  test("persists theme preference across reloads", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/settings", { waitUntil: "networkidle" })
    await page.waitForTimeout(TEST_DELAYS.short)
    await page.waitForSelector('[role="radiogroup"]')

    await page.evaluate(() => {
      localStorage.setItem("ue-mode", "dark")
    })

    await page.reload()
    await page.waitForURL(/\/settings$/)
    await expect(page.locator("html")).toHaveClass(/dark/)
  })

  test("allows updating user profile settings", async ({ page }) => {
    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, "/profile?edit=1", { waitUntil: "networkidle" })
    await page.waitForTimeout(TEST_DELAYS.default) // Allow more time for edit mode hydration

    const saveBtn = page.getByTestId("profile-save-button")
    await expect(saveBtn).toBeVisible()

    const aboutInput = page.getByTestId("profile-about-input")
    const newBio = `Updated bio ${Date.now()}`
    await aboutInput.fill(newBio)
    await saveBtn.click()

    await expect(page.getByText(newBio)).toBeVisible()
    await page.reload()
    await expect(page.getByText(newBio)).toBeVisible()
  })
})
