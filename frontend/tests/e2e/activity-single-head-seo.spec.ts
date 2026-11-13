import type { Page } from "@playwright/test"
import { expect, test } from "./test"
import { useMockApi } from "./utils/mockApi"

// AUD-432 regression: the Activity page must own exactly one <title>,
// description and og:title in <head>. Root brand fallback metadata and page
// metadata must never coexist, both on hydration and during client navigation.
// Unit tests run without a real browser, so this lane samples the live head.

const ACTIVITY_TITLE_BY_LANG: Record<string, string> = {
  en: "Activity | University Ecosystem",
  ru: "Активность | University Ecosystem",
}

const ACTIVITY_TITLE_PATTERN = /^(Активность|Activity) \| University Ecosystem$/

const SAMPLE_WINDOW_MS = 3_000
const SAMPLE_INTERVAL_MS = 300

type HeadSnapshot = {
  lang: string
  title: string
  titles: number
  descriptions: number
  ogTitles: number
}

async function readHeadSnapshot(page: Page): Promise<HeadSnapshot> {
  return page.evaluate(() => ({
    lang: document.documentElement.lang,
    title: document.title,
    titles: document.head.querySelectorAll("title").length,
    descriptions: document.head.querySelectorAll('meta[name="description"]').length,
    ogTitles: document.head.querySelectorAll('meta[property="og:title"]').length,
  }))
}

async function sampleHeadForWindow(page: Page): Promise<HeadSnapshot[]> {
  const samples: HeadSnapshot[] = []
  for (let elapsed = 0; elapsed < SAMPLE_WINDOW_MS; elapsed += SAMPLE_INTERVAL_MS) {
    samples.push(await readHeadSnapshot(page))
    await page.waitForTimeout(SAMPLE_INTERVAL_MS)
  }
  return samples
}

function expectSingleActivitySeoWindow(samples: HeadSnapshot[]): void {
  const violations = samples.filter(
    (sample) => sample.titles !== 1 || sample.descriptions !== 1 || sample.ogTitles !== 1
  )
  expect(violations).toEqual([])

  const last = samples.at(-1)
  expect(last).toBeDefined()
  expect(last?.title).toBe(ACTIVITY_TITLE_BY_LANG[last?.lang ?? ""])
}

test.describe("Activity single head SEO", () => {
  test("a full load of /activity keeps one page SEO set through hydration", async ({ page }) => {
    await useMockApi(page, { authenticated: true })

    await page.goto("/activity", { waitUntil: "domcontentloaded" })
    await page.waitForFunction(() => window.__APP_HYDRATED === true, null, {
      timeout: 15_000,
    })
    // An unauthenticated first paint can pass through /login and the brand
    // fallback before the Activity route settles. Sample only the settled
    // window, which is the state the regression concerns.
    await page.waitForURL(/\/activity$/)
    await expect.poll(() => page.title()).toMatch(ACTIVITY_TITLE_PATTERN)

    expectSingleActivitySeoWindow(await sampleHeadForWindow(page))
  })

  test("client navigation to /activity keeps one page SEO set", async ({ page, isMobile }) => {
    await useMockApi(page, { authenticated: true })

    await page.goto("/dashboard", { waitUntil: "domcontentloaded" })
    await page.waitForFunction(() => window.__APP_HYDRATED === true, null, {
      timeout: 15_000,
    })
    // WebKit can report hydration before the Dashboard route has written its
    // head, so wait for the settled start state instead of reading it once.
    // The regression itself is asserted on every sample after navigation.
    await page.waitForURL(/\/dashboard$/)
    await expect
      .poll(async () => {
        const snapshot = await readHeadSnapshot(page)
        return [snapshot.titles, snapshot.descriptions]
      })
      .toEqual([1, 1])

    // Navigate inside the SPA so the Activity route passes through its
    // pending state rather than a document load.
    // At desktop width Activity sits in the overflow navigation; at mobile
    // width the bottom bar has no Activity entry, so it lives in the drawer.
    if (isMobile) {
      await page.locator('button[aria-controls="mobile-drawer"]').click()
    } else {
      await page.getByRole("button", { name: /Дополнительная навигация|More navigation/ }).click()
    }
    await page.locator('a[href="/activity"]:visible').first().click()
    await expect(page).toHaveURL(/\/activity$/)

    expectSingleActivitySeoWindow(await sampleHeadForWindow(page))
  })
})
