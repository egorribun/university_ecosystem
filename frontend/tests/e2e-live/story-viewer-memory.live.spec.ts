import { expect, loginAs, test } from "./fixtures"
import type { CDPSession, Page } from "@playwright/test"

const SEEDED_STORY_TITLE = /(?:Сессия: советы по подготовке|Exam season: preparation tips)/u
const WARM_UP_CYCLES = 1
const MEASURED_CYCLES = 20
const HEAP_PLATEAU_TOLERANCE_BYTES = 512 * 1024

type DOMCounters = {
  documents: number
  nodes: number
  jsEventListeners: number
}

type MemorySnapshot = {
  domCounters: DOMCounters
  jsHeapUsedBytes: number
}

async function settleViewerCleanup(page: Page, cdp: CDPSession): Promise<MemorySnapshot> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve) => {
        window.requestAnimationFrame(() => window.requestAnimationFrame(() => resolve()))
      })
  )
  await cdp.send("HeapProfiler.collectGarbage")
  const [domCounters, heapUsage] = await Promise.all([
    cdp.send("Memory.getDOMCounters") as Promise<DOMCounters>,
    cdp.send("Runtime.getHeapUsage") as Promise<{ usedSize: number }>,
  ])
  return { domCounters, jsHeapUsedBytes: heapUsage.usedSize }
}

test("a seeded story viewer reaches a memory plateau after 20 open-close cycles", async ({
  page,
}) => {
  await loginAs(page, "student")
  await page.goto("/dashboard")

  const trigger = page.getByRole("button", { name: SEEDED_STORY_TITLE })
  const dialog = page.getByRole("dialog")
  await expect(trigger).toBeVisible()
  const storyWriteRequests: string[] = []
  page.on("request", (request) => {
    const requestUrl = new URL(request.url())
    if (
      requestUrl.pathname.startsWith("/api/v1/stories") &&
      !["GET", "HEAD"].includes(request.method())
    ) {
      storyWriteRequests.push(`${request.method()} ${requestUrl.pathname}`)
    }
  })
  const initialBodyOverflow = await page.locator("body").evaluate((body) => body.style.overflow)
  const cdp = await page.context().newCDPSession(page)

  const openAndClose = async (verifyHiddenPause = false): Promise<MemorySnapshot> => {
    await trigger.click()
    await expect(dialog).toBeVisible()
    await expect(dialog).toHaveCount(1)
    await expect(dialog).toHaveAccessibleName(SEEDED_STORY_TITLE)

    const activeProgress = dialog.locator('[role="progressbar"][aria-live="polite"]')
    const readProgress = async () => Number(await activeProgress.getAttribute("aria-valuenow"))
    await expect.poll(readProgress).toBeGreaterThan(0)

    if (verifyHiddenPause) {
      const backgroundPage = await page.context().newPage()
      try {
        await backgroundPage.goto("about:blank")
        await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("hidden")
        const hiddenProgress = await readProgress()
        await backgroundPage.waitForTimeout(1_000)
        expect(await readProgress()).toBe(hiddenProgress)

        await page.bringToFront()
        await expect.poll(() => page.evaluate(() => document.visibilityState)).toBe("visible")
        await expect.poll(readProgress).toBeGreaterThan(hiddenProgress)
      } finally {
        await backgroundPage.close()
        await page.bringToFront()
      }
    }

    await page.keyboard.press("Escape")
    await expect(dialog).toHaveCount(0)
    await expect(trigger).toBeFocused()
    await expect
      .poll(() => page.locator("body").evaluate((body) => body.style.overflow))
      .toBe(initialBodyOverflow)

    return settleViewerCleanup(page, cdp)
  }

  try {
    for (let cycle = 0; cycle < WARM_UP_CYCLES; cycle += 1) {
      await openAndClose()
    }

    const warmSnapshot = await settleViewerCleanup(page, cdp)
    const measuredHeapSamples: number[] = []
    for (let cycle = 0; cycle < MEASURED_CYCLES; cycle += 1) {
      const snapshot = await openAndClose(cycle === 0)
      expect(snapshot.domCounters).toEqual(warmSnapshot.domCounters)
      measuredHeapSamples.push(snapshot.jsHeapUsedBytes)
    }
    expect(storyWriteRequests).toEqual([])

    const earlyHeapMean =
      measuredHeapSamples.slice(0, 5).reduce((total, bytes) => total + bytes, 0) / 5
    const lateHeapMean =
      measuredHeapSamples.slice(-5).reduce((total, bytes) => total + bytes, 0) / 5
    expect(lateHeapMean).toBeLessThanOrEqual(earlyHeapMean + HEAP_PLATEAU_TOLERANCE_BYTES)
  } finally {
    await cdp.detach()
  }
})
