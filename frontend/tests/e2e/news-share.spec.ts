import { devices, expect, test } from "./test"
import { MOCK_NEWS_ID, useMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"

const newsPath = `/news/${MOCK_NEWS_ID}`

test.describe("News detail sharing (desktop)", () => {
  test("falls back to copying link when the Web Share API is unavailable", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "share", {
        value: undefined,
        configurable: true,
      })

      Object.defineProperty(navigator, "clipboard", {
        value: {
          writeText: (text: string) => {
            ;(window as typeof window & { __copiedLink?: string }).__copiedLink = text
            return Promise.resolve()
          },
        },
        configurable: true,
      })
    })

    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, newsPath)
    await expect(
      page.getByRole("heading", { name: /(Новость дня|News of the day)/i })
    ).toBeVisible()

    const shareButton = page.getByRole("button", { name: /(Поделиться|Share)/i })
    await expect(shareButton).toBeVisible()
    await shareButton.click()

    // When share API is undefined, a dialog opens. We need to click "Copy link".
    await page.getByRole("button", { name: /Скопировать ссылку|Copy link/i }).click()

    await expect(page.getByText(/Ссылка скопирована|Link copied/i).first()).toBeVisible()
    const copiedLink = await page.evaluate(
      () => (window as typeof window & { __copiedLink?: string }).__copiedLink
    )
    expect(copiedLink).toContain(newsPath)
  })
})

// Firefox does not support the isMobile context option; strip it while
// preserving the mobile viewport, userAgent, deviceScaleFactor, and touch emulation.
const {
  defaultBrowserType: _ignore,
  isMobile: _isMobile,
  ...iPhone13Pro
} = devices["iPhone 13 Pro"]

test.describe("News detail sharing (mobile)", () => {
  test.use(iPhone13Pro)

  test("uses the Web Share API when available", async ({ page }) => {
    await page.addInitScript(() => {
      Object.defineProperty(navigator, "share", {
        value: (data: ShareData) => {
          const globalWindow = window as typeof window & { __sharedPayloads?: ShareData[] }
          globalWindow.__sharedPayloads = [...(globalWindow.__sharedPayloads ?? []), data]
          return Promise.resolve()
        },
        configurable: true,
      })
    })

    const mock = await useMockApi(page)
    await mock.login(page)

    await gotoWithTransientRetry(page, newsPath)
    await expect(
      page.getByRole("heading", { name: /(Новость дня|News of the day)/i })
    ).toBeVisible()

    const shareButton = page.getByRole("button", { name: /(Поделиться|Share)/i })
    await expect(shareButton).toBeVisible()
    await shareButton.click()

    await expect(page.getByText(/Окно отправки открыто|Share sheet opened/i)).toBeVisible()
    const sharedPayload = await page.evaluate(() =>
      (window as typeof window & { __sharedPayloads?: ShareData[] }).__sharedPayloads?.at(0)
    )
    expect(sharedPayload?.url).toContain(newsPath)
    expect(sharedPayload?.title).toBeTruthy()
  })
})
