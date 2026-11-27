import { expect } from "@playwright/test"
import { test, verifyRapidDrawerNavigation } from "./mobile-drawer-fixture"
import { useMockApi } from "./utils/mockApi"

for (const input of ["touch", "mouse"] as const) {
  test.describe(`${input} input`, () => {
    test.use({ viewport: { width: 390, height: 844 }, hasTouch: input === "touch" })

    for (const reducedMotion of ["no-preference", "reduce"] as const) {
      test(`mobile drawer switches rapidly with ${reducedMotion} motion`, async ({
        page,
        drawerPhase,
      }) => {
        drawerPhase.setCase(input, reducedMotion)
        drawerPhase.mark("media")
        await page.emulateMedia({ reducedMotion })
        drawerPhase.mark("mock-api")
        await useMockApi(page)
        drawerPhase.mark("route")
        await page.goto("/events")
        drawerPhase.mark("main")
        await expect(page.getByRole("main")).toBeVisible()
        await verifyRapidDrawerNavigation(page, input === "touch", drawerPhase)
      })
    }
  })
}
