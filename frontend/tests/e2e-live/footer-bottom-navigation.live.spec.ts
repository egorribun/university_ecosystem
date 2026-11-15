import { expect, loginAs, test } from "./fixtures"
import type { ConsoleMessage, Page } from "@playwright/test"
import { reportLiveFooterGeometry } from "./live-ui-diagnostic"

const NAVIGATION_PATHS = ["/dashboard", "/news", "/events", "/schedule", "/profile"] as const
const SHORT_ACTIVITY_EMPTY_STATE = '.activity-theme section[aria-live="polite"]'
const SEEDED_LONG_ARTICLE =
  /ГУУ вошёл в топ-20 лучших университетов страны|GUU ranks among the country's top 20 universities/u

test.use({ trace: "off", screenshot: "off", video: "off" })

async function waitForStableViewportLayout(page: Page): Promise<void> {
  await page.evaluate(
    () =>
      new Promise<void>((resolve, reject) => {
        const navigation = document.querySelector<HTMLElement>(
          'nav:has(a[data-tab-key="/dashboard"])'
        )
        if (navigation === null) {
          reject(new Error("mobile navigation is missing after viewport resize"))
          return
        }

        const sample = () => {
          const navigationRect = navigation.getBoundingClientRect()
          const bodyRect = document.body.getBoundingClientRect()
          return [
            window.innerWidth,
            window.innerHeight,
            bodyRect.left,
            bodyRect.right,
            bodyRect.width,
            navigationRect.left,
            navigationRect.right,
            navigationRect.top,
            navigationRect.bottom,
            navigationRect.width,
          ].map((value) => Math.round(value * 100))
        }

        let previous = sample()
        let stableFrames = 0
        const check = () => {
          const current = sample()
          if (current.every((value, index) => value === previous[index])) {
            stableFrames += 1
          } else {
            stableFrames = 0
          }
          if (stableFrames >= 2) {
            resolve()
            return
          }
          previous = current
          window.requestAnimationFrame(check)
        }
        window.requestAnimationFrame(check)
      })
  )
}

async function verifyFooterDoesNotOverlapBottomNavigation(page: Page): Promise<void> {
  const footer = page.getByRole("contentinfo")
  const bottomNavigation = page.locator('nav:has(a[data-tab-key="/dashboard"])')
  await expect(footer).toBeVisible()
  await expect(bottomNavigation).toBeVisible()

  await page.evaluate(() => window.scrollTo(0, document.documentElement.scrollHeight))
  await expect
    .poll(() =>
      page.evaluate(
        () => document.documentElement.scrollHeight - window.innerHeight - window.scrollY
      )
    )
    .toBeLessThanOrEqual(1)

  const geometry = await page.evaluate(() => {
    const footerElement = document.querySelector<HTMLElement>('footer[role="contentinfo"]')
    const navElement = document.querySelector<HTMLElement>('nav:has(a[data-tab-key="/dashboard"])')
    if (!footerElement || !navElement) throw new Error("production footer or mobile nav is missing")
    const footerRect = footerElement.getBoundingClientRect()
    const navRect = navElement.getBoundingClientRect()
    return {
      footerBottom: footerRect.bottom,
      navTop: navRect.top,
      navBottom: navRect.bottom,
      viewportHeight: window.innerHeight,
    }
  })

  expect(geometry.navBottom).toBeCloseTo(geometry.viewportHeight, 0)
  expect(
    geometry.footerBottom,
    "footer should clear the fixed bottom navigation"
  ).toBeLessThanOrEqual(geometry.navTop + 1)
}

test("bottom navigation fits phones and the navbar drawer works at the tablet boundary", async ({
  page,
}, testInfo) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loginAs(page, "student")
  await page.goto("/dashboard")
  await expect(page.getByRole("main")).toBeVisible()

  const bottomNavigation = page.locator('nav:has(a[data-tab-key="/dashboard"])')
  for (const width of [390, 360]) {
    await page.setViewportSize({ width, height: 844 })
    await expect(bottomNavigation).toBeVisible()
    await waitForStableViewportLayout(page)
    const navigationRect = await bottomNavigation.evaluate((element) => {
      const rect = element.getBoundingClientRect()
      const nav = element as HTMLElement
      const navStyle = window.getComputedStyle(nav)
      const matrix =
        navStyle.transform === "none"
          ? null
          : (() => {
              try {
                return new DOMMatrixReadOnly(navStyle.transform)
              } catch {
                return null
              }
            })()
      let fixedContainingBlock: Element | null = null
      let fixedContainingBlockDepth = 0
      let depth = 0
      for (
        let ancestor = nav.parentElement;
        ancestor !== null && depth < 32;
        ancestor = ancestor.parentElement
      ) {
        depth += 1
        const style = window.getComputedStyle(ancestor)
        const containCreatesBlock = /(?:^|\s)(?:layout|paint|strict|content)(?:\s|$)/u.test(
          style.contain
        )
        const willChangeCreatesBlock = style.willChange
          .split(",")
          .some((value) =>
            /^(?:transform|perspective|filter|backdrop-filter|contain|content-visibility)$/u.test(
              value.trim()
            )
          )
        const backdropFilter = style.getPropertyValue("backdrop-filter")
        const containerType = style.getPropertyValue("container-type")
        const contentVisibility = style.getPropertyValue("content-visibility")
        if (
          style.transform !== "none" ||
          style.perspective !== "none" ||
          style.filter !== "none" ||
          (backdropFilter !== "" && backdropFilter !== "none") ||
          (containerType !== "" && containerType !== "normal") ||
          (contentVisibility !== "" && contentVisibility !== "visible") ||
          containCreatesBlock ||
          willChangeCreatesBlock
        ) {
          fixedContainingBlock = ancestor
          fixedContainingBlockDepth = depth
          break
        }
      }
      const containingBlockRect = fixedContainingBlock?.getBoundingClientRect()
      const translateValue = navStyle.getPropertyValue("translate")
      return {
        left: rect.left,
        right: rect.right,
        top: rect.top,
        bottom: rect.bottom,
        width: rect.width,
        innerWidth: window.innerWidth,
        innerHeight: window.innerHeight,
        clientWidth: document.documentElement.clientWidth,
        scrollWidth: document.documentElement.scrollWidth,
        usableLayoutLeft: document.body.getBoundingClientRect().left,
        usableLayoutRight: document.body.getBoundingClientRect().right,
        usableLayoutWidth: document.body.getBoundingClientRect().width,
        position: navStyle.position,
        navTransformPresent:
          navStyle.transform !== "none" || (translateValue !== "" && translateValue !== "none"),
        navTransformX: matrix === null ? 0 : matrix.is2D ? matrix.e : matrix.m41,
        navTransformY: matrix === null ? 0 : matrix.is2D ? matrix.f : matrix.m42,
        fixedContainingBlockFound: fixedContainingBlock !== null,
        fixedContainingBlockDepth,
        containingBlockLeft: containingBlockRect?.left ?? 0,
        containingBlockRight: containingBlockRect?.right ?? 0,
        containingBlockTop: containingBlockRect?.top ?? 0,
        containingBlockBottom: containingBlockRect?.bottom ?? 0,
      }
    })
    reportLiveFooterGeometry(
      testInfo.project.name,
      width,
      844,
      navigationRect.innerWidth,
      navigationRect.innerHeight,
      navigationRect.clientWidth,
      navigationRect.scrollWidth,
      navigationRect.left,
      navigationRect.right,
      navigationRect.top,
      navigationRect.bottom,
      navigationRect.width,
      navigationRect.navTransformPresent,
      navigationRect.navTransformX,
      navigationRect.navTransformY,
      navigationRect.fixedContainingBlockFound,
      navigationRect.fixedContainingBlockDepth,
      navigationRect.containingBlockLeft,
      navigationRect.containingBlockRight,
      navigationRect.containingBlockTop,
      navigationRect.containingBlockBottom
    )
    expect(navigationRect.position, width + "px nav remains fixed").toBe("fixed")
    expect(navigationRect.left, `${width}px nav left edge`).toBeCloseTo(0, 0)
    expect(navigationRect.right, width + "px nav right edge").toBeCloseTo(
      navigationRect.usableLayoutRight,
      0
    )
    expect(navigationRect.width, width + "px nav usable width").toBeCloseTo(
      navigationRect.usableLayoutWidth,
      0
    )
    expect(
      navigationRect.scrollWidth,
      width + "px page should not overflow its usable layout viewport"
    ).toBeLessThanOrEqual(navigationRect.usableLayoutWidth + 1)
    expect(navigationRect.top, `${width}px nav height`).toBeLessThanOrEqual(844 - 64)
    expect(navigationRect.bottom, `${width}px nav bottom edge`).toBeCloseTo(844, 0)

    for (const path of NAVIGATION_PATHS) {
      const link = bottomNavigation.locator(`a[data-tab-key="${path}"]`)
      await expect(link).toBeVisible()
      const target = await link.evaluate((element) => {
        const rect = element.getBoundingClientRect()
        return { width: rect.width, height: rect.height }
      })
      expect(target.width, `${width}px ${path} target width`).toBeGreaterThanOrEqual(44)
      expect(target.height, `${width}px ${path} target height`).toBeGreaterThanOrEqual(44)
    }

    await verifyRapidMobileNavigation(page, testInfo.project.use.hasTouch === true)
  }

  const keyboardNewsLink = bottomNavigation.locator('a[data-tab-key="/news"]')
  await keyboardNewsLink.focus()
  await page.keyboard.press("Enter")
  await expect(page).toHaveURL(/\/news\/?$/u)
  await expect(bottomNavigation.locator('a[data-tab-key="/news"]')).toHaveAttribute(
    "aria-current",
    "page"
  )

  await page.setViewportSize({ width: 1024, height: 900 })
  await expect(bottomNavigation).toBeHidden()
  const navbar = page.locator("nav.vt-navbar")
  await expect(navbar).toBeVisible()
  const drawerTrigger = page.locator('button[aria-controls="mobile-drawer"]')
  await expect(drawerTrigger).toBeVisible()
  await expect(drawerTrigger).toHaveAttribute("aria-expanded", "false")
  await expect(navbar.locator(".navbar-desktop-nav")).toHaveCount(0)
  const drawerTriggerSize = await drawerTrigger.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return { width: rect.width, height: rect.height }
  })
  expect(drawerTriggerSize.width).toBeGreaterThanOrEqual(44)
  expect(drawerTriggerSize.height).toBeGreaterThanOrEqual(44)
  const shell = await navbar.evaluate((element) => {
    const rect = element.getBoundingClientRect()
    return {
      left: rect.left,
      right: rect.right,
      clientWidth: element.clientWidth,
      scrollWidth: element.scrollWidth,
    }
  })
  expect(shell.left).toBeGreaterThanOrEqual(0)
  expect(shell.right).toBeLessThanOrEqual(1024)
  expect(shell.scrollWidth).toBeLessThanOrEqual(shell.clientWidth + 1)
})

test("footer clears the bottom navigation on short and long production pages", async ({ page }) => {
  await page.setViewportSize({ width: 390, height: 844 })
  await loginAs(page, "student")

  await page.goto("/activity")
  await expect(page.locator(".activity-theme")).toBeVisible()
  // The demo seed intentionally has no attendance, grade, or participation
  // records, so this route exercises the real short-content empty state.
  await expect(page.locator(SHORT_ACTIVITY_EMPTY_STATE)).toBeVisible()
  const shortContentHeight = await page
    .locator(".activity-theme")
    .evaluate((element) => element.getBoundingClientRect().height)
  expect(shortContentHeight, "activity empty state should remain a short page").toBeLessThan(844)

  const shortPageFooterTop = await page
    .getByRole("contentinfo")
    .evaluate((element) => element.getBoundingClientRect().top)
  expect(shortPageFooterTop).toBeGreaterThan(844)
  await verifyFooterDoesNotOverlapBottomNavigation(page)

  await page.goto("/news")
  const articleLink = page.getByRole("link", { name: SEEDED_LONG_ARTICLE })
  await expect(articleLink).toBeVisible()
  await articleLink.click()
  await expect(page).toHaveURL(/\/news\/[^/]+$/u)
  await expect(page.getByRole("heading", { name: SEEDED_LONG_ARTICLE })).toBeVisible()
  await expect
    .poll(() =>
      page.evaluate(
        () => (document.querySelector("main")?.scrollHeight ?? 0) > window.innerHeight * 1.5
      )
    )
    .toBe(true)
  await verifyFooterDoesNotOverlapBottomNavigation(page)
})

// Extend the existing collected scenario: no new live test identity, project skip,
// fixture, retry, or timeout. Coordinates are captured before the burst so input
// delivery never waits for an intermediate route, locator, or animation.
async function verifyRapidMobileNavigation(page: Page, hasTouch: boolean): Promise<void> {
  const bottomNavigation = page.locator('nav:has(a[data-tab-key="/dashboard"])')
  const rapidPaths = ["/events", "/schedule", "/profile", "/news"] as const
  const points = []
  for (const path of rapidPaths) {
    const link = bottomNavigation.locator(`a[data-tab-key="${path}"]`)
    await expect(link).toBeVisible()
    const box = await link.boundingBox()
    if (box === null) throw new Error("rapid navigation target has no hit area")
    points.push({ x: box.x + box.width / 2, y: box.y + box.height / 2 })
  }

  const newsHeading = page.getByRole("main").getByRole("heading", {
    name: /^(?:Новости университета|University news)[ 0-9]*$/u,
  })
  const eventsTabs = page.getByRole("main").getByRole("tablist", { name: /Мероприятия|Events/u })
  const expectCurrentRoute = async (path: "/news" | "/events") => {
    await expect.poll(() => new URL(page.url()).pathname).toBe(path)
    await expect(bottomNavigation.locator('a[aria-current="page"]')).toHaveCount(1)
    await expect(bottomNavigation.locator(`a[data-tab-key="${path}"]`)).toHaveAttribute(
      "aria-current",
      "page"
    )
    await expect(path === "/news" ? newsHeading : eventsTabs).toBeVisible()
    await expect(path === "/news" ? eventsTabs : newsHeading).toHaveCount(0)
  }

  let consoleErrorCount = 0
  const onConsole = (message: ConsoleMessage) => {
    if (message.type() === "error") consoleErrorCount += 1
  }
  page.on("console", onConsole)
  try {
    // Native browser input, not DOM.click/dispatchEvent. Await only input
    // dispatch; there are deliberately no navigation waits between these taps.
    for (const point of points) {
      if (hasTouch) await page.touchscreen.tap(point.x, point.y)
      else await page.mouse.click(point.x, point.y)
    }
    await expectCurrentRoute("/news")

    const historyLength = await page.evaluate(() => window.history.length)
    const newsPoint = points[3]
    if (newsPoint === undefined) throw new Error("rapid news target is missing")
    for (let activation = 0; activation < 2; activation += 1) {
      if (hasTouch) await page.touchscreen.tap(newsPoint.x, newsPoint.y)
      else await page.mouse.click(newsPoint.x, newsPoint.y)
    }
    await expectCurrentRoute("/news")
    await expect.poll(() => page.evaluate(() => window.scrollY)).toBe(0)
    expect(await page.evaluate(() => window.history.length)).toBe(historyLength)

    // The drawer supplies a settled, known history boundary. Intermediate
    // entries from the rapid burst are intentionally not assumed to commit.
    const drawerTrigger = page.locator('button[aria-controls="mobile-drawer"]')
    if (hasTouch) await drawerTrigger.tap()
    else await drawerTrigger.click()
    const drawer = page.locator('#mobile-drawer[role="dialog"]')
    await expect(drawer).toBeVisible()
    await expect(drawerTrigger).toHaveAttribute("aria-expanded", "true")
    const drawerEvents = drawer.locator("#mobile-nav-link-events")
    if (hasTouch) await drawerEvents.tap()
    else await drawerEvents.click()
    await expectCurrentRoute("/events")
    await expect(drawer).toHaveCount(0)
    await expect(drawerTrigger).toHaveAttribute("aria-expanded", "false")

    await page.goBack()
    await expectCurrentRoute("/news")
    await expect(drawer).toHaveCount(0)
    await page.goForward()
    await expectCurrentRoute("/events")
    await expect(drawer).toHaveCount(0)
    expect(consoleErrorCount, "rapid navigation must not emit console errors").toBe(0)
  } finally {
    page.off("console", onConsole)
  }
}
