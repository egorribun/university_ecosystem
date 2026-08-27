import { expect, test, type Page } from "@playwright/test"

const MARK_RESET_TIME_MS = 5_700
const FAILSAFE_END_TIME_MS = 12_002

async function holdApplicationScripts(page: Page) {
  let releaseGate: () => void = () => {}
  let released = false
  const gate = new Promise<void>((resolve) => {
    releaseGate = resolve
  })

  await page.route("**/*", async (route) => {
    const request = route.request()
    const requestUrl = new URL(request.url())
    const isApplicationEntry =
      request.resourceType() === "script" && /\/assets\/index-[^/]+\.js$/.test(requestUrl.pathname)
    if (isApplicationEntry && !released) {
      await gate
    }
    await route.continue()
  })

  return async () => {
    if (released) return
    released = true
    releaseGate()
    // Keep the pass-through route installed after releasing the gate. WebKit
    // can still have a module request in flight when the gate resolves;
    // unrouteAll() immediately aborts that request before its handler reaches
    // `route.continue()`, leaving the document in its unstyled SSR shell and
    // preventing the hydration sentinel from being published. The route now
    // continues every subsequent request and is cleaned up with the page.
  }
}

async function freezeMarkAt(page: Page, milliseconds: number) {
  await page.locator(".brand-boot-loader__mark").evaluate((mark, currentTime) => {
    for (const animation of mark.getAnimations({ subtree: true })) {
      animation.pause()
      animation.currentTime = currentTime
    }
  }, milliseconds)
}

test("renders the SSR loader before JavaScript and keeps status through mark reset", async ({
  page,
}) => {
  const releaseScripts = await holdApplicationScripts(page)

  try {
    await page.goto("/", { waitUntil: "commit" })

    const loader = page.locator("[data-brand-boot-loader]")
    const mark = page.locator(".brand-boot-loader__mark")
    const status = page.locator(".brand-boot-loader__status")
    await expect(loader).toBeVisible()
    await expect(loader).toHaveAttribute("data-state", "active")
    await expect(loader.getByText("Загрузка")).toBeVisible()

    const animationContract = await mark.evaluate((element) =>
      element.getAnimations({ subtree: true }).map((animation) => ({
        delay: animation.effect?.getTiming().delay,
        name: animation instanceof CSSAnimation ? animation.animationName : "",
      }))
    )
    expect(
      animationContract.filter((animation) => animation.name === "brand-boot-loader-mark-exit")
    ).toHaveLength(1)
    expect(
      animationContract.find((animation) => animation.name === "brand-boot-loader-red-body")?.delay
    ).toBe(0)

    await freezeMarkAt(page, MARK_RESET_TIME_MS)
    await expect.poll(() => mark.evaluate((element) => getComputedStyle(element).opacity)).toBe("0")
    await expect
      .poll(() => status.evaluate((element) => getComputedStyle(element).opacity))
      .toBe("1")

    await freezeMarkAt(page, 3_000)
    for (const viewport of [
      { width: 320, height: 568 },
      { width: 568, height: 320 },
      { width: 768, height: 1_024 },
      { width: 1_440, height: 900 },
      { width: 3_840, height: 2_160 },
    ]) {
      await page.setViewportSize(viewport)
      const metrics = await loader.evaluate((element) => {
        const content = element
          .querySelector(".brand-boot-loader__content")
          ?.getBoundingClientRect()
        const markHolder = element
          .querySelector(".brand-boot-loader__mark-holder")
          ?.getBoundingClientRect()
        return {
          documentScrollbarWidth: window.innerWidth - document.documentElement.clientWidth,
          contentBottom: content?.bottom ?? -1,
          contentTop: content?.top ?? -1,
          documentOverflow: document.documentElement.scrollWidth > window.innerWidth,
          loaderOverflow: element.scrollWidth > element.clientWidth,
          markWidth: markHolder?.width ?? -1,
          viewportHeight: window.innerHeight,
        }
      })

      expect(metrics.documentOverflow).toBe(false)
      expect(metrics.documentScrollbarWidth).toBe(0)
      expect(metrics.loaderOverflow).toBe(false)
      expect(metrics.markWidth).toBeGreaterThanOrEqual(143)
      expect(metrics.markWidth).toBeLessThanOrEqual(481)
      expect(metrics.contentTop).toBeGreaterThanOrEqual(0)
      expect(metrics.contentBottom).toBeLessThanOrEqual(metrics.viewportHeight)

      if (viewport.width === 3_840) {
        expect(metrics.markWidth).toBeGreaterThanOrEqual(475)
        expect(metrics.markWidth).toBeLessThanOrEqual(481)
      }
    }
  } finally {
    await releaseScripts()
  }
})

test("exits after hydration without a mismatch or lingering hit target", async ({ page }) => {
  const hydrationProblems: string[] = []
  page.on("console", (message) => {
    if (/hydration|react error #418|did not match|didn't match|recoverable/i.test(message.text())) {
      hydrationProblems.push(message.text())
    }
  })
  page.on("pageerror", (error) => {
    if (/hydration|react error #418|did not match|didn't match|recoverable/i.test(error.message)) {
      hydrationProblems.push(error.message)
    }
  })

  const releaseScripts = await holdApplicationScripts(page)
  await page.goto("/", { waitUntil: "commit" })
  const loader = page.locator("[data-brand-boot-loader]")
  await expect(loader).toBeVisible()

  await releaseScripts()
  await page.waitForFunction(() => window.__APP_HYDRATED === true)
  await expect(loader).toHaveCount(0, { timeout: 2_000 })
  expect(hydrationProblems).toEqual([])
})

test("uses a complete static mark for reduced motion", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce", colorScheme: "dark" })
  const releaseScripts = await holdApplicationScripts(page)

  try {
    await page.goto("/", { waitUntil: "commit" })

    const loader = page.locator("[data-brand-boot-loader]")
    await expect(loader).toBeVisible()
    await expect(page.locator(".brand-boot-loader__body-path").first()).toHaveCSS(
      "fill-opacity",
      "1"
    )
    await expect(page.locator(".brand-boot-loader__status")).toHaveCSS("opacity", "1")
    expect(
      await page
        .locator(".brand-boot-loader__mark")
        .evaluate((element) => element.getAnimations({ subtree: true }).length)
    ).toBe(0)
  } finally {
    await releaseScripts()
  }
})

test("reveals the SSR application after the CSS-only failsafe", async ({ page }) => {
  const releaseScripts = await holdApplicationScripts(page)

  try {
    await page.goto("/", { waitUntil: "commit" })

    const loader = page.locator("[data-brand-boot-loader]")
    await expect(loader).toBeVisible()
    await loader.evaluate(async (element, currentTime) => {
      const failsafe = element
        .getAnimations()
        .find(
          (animation) =>
            animation instanceof CSSAnimation &&
            animation.animationName === "brand-boot-loader-failsafe"
        )
      if (!failsafe) {
        throw new Error("Brand loader failsafe animation is missing")
      }
      failsafe.pause()
      await failsafe.ready
      failsafe.currentTime = currentTime
    }, FAILSAFE_END_TIME_MS)
    await page.locator("html").evaluate(async (element, currentTime) => {
      const scrollUnlock = element
        .getAnimations()
        .find(
          (animation) =>
            animation instanceof CSSAnimation &&
            animation.animationName === "brand-boot-loader-scroll-unlock"
        )
      if (!scrollUnlock) {
        throw new Error("Brand loader scroll-unlock animation is missing")
      }
      scrollUnlock.pause()
      await scrollUnlock.ready
      scrollUnlock.currentTime = currentTime
    }, FAILSAFE_END_TIME_MS)

    await expect(loader).toHaveCSS("visibility", "hidden")
    await expect(loader).toHaveCSS("pointer-events", "none")
    await expect(page.locator("html")).toHaveCSS("overflow-y", "auto")
  } finally {
    await releaseScripts()
  }
})

test("matches the pre-paint dark theme without a background flash", async ({ page }) => {
  await page.addInitScript(() => localStorage.setItem("ue-mode", "dark"))
  const releaseScripts = await holdApplicationScripts(page)

  try {
    await page.goto("/", { waitUntil: "commit" })

    const loader = page.locator("[data-brand-boot-loader]")
    await expect(loader).toBeVisible()
    const colors = await loader.evaluate((element) => ({
      initial: getComputedStyle(document.documentElement).getPropertyValue("--initial-bg").trim(),
      loader: getComputedStyle(element).backgroundColor,
    }))
    expect(colors.loader).toBe("rgb(2, 6, 23)")
    expect(colors.initial).toBe("#020617")
  } finally {
    await releaseScripts()
  }
})
