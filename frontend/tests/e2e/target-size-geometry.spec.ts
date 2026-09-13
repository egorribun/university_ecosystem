import { expect, test } from "./test"

import { gotoWithTransientRetry } from "./utils/navigation"
import { useMockApi } from "./utils/mockApi"
import { assertControlTarget } from "./utils/targetSize"

const ENABLED = process.env.TARGET_SIZE_E2E === "true"
const HOST = process.env.PLAYWRIGHT_HOST ?? "127.0.0.1"
const PORT = process.env.PLAYWRIGHT_PORT ?? "5173"
const BASE_URL = process.env.PLAYWRIGHT_BASE_URL ?? `http://${HOST}:${PORT}`
const VIEWPORTS = [
  { height: 800, width: 360 },
  { height: 844, width: 390 },
] as const

if (ENABLED) {
  test.describe("Target-size geometry", () => {
    test("foundation targets — navbar actions", async ({ browser }) => {
      for (const viewport of VIEWPORTS) {
        await test.step(`${viewport.width}x${viewport.height}`, async () => {
          const context = await browser.newContext({ baseURL: BASE_URL, viewport })
          const page = await context.newPage()
          try {
            const mock = await useMockApi(page)
            await mock.login(page)
            await expect(page.locator("#main-content")).toBeVisible()

            await assertControlTarget(
              page.locator("#global-messenger-btn"),
              `${viewport.width}px navbar messenger action`
            )
            await assertControlTarget(
              page.locator("#global-notifications-btn"),
              `${viewport.width}px navbar notifications action`
            )
            await assertControlTarget(
              page.locator('button[aria-controls="mobile-drawer"]'),
              `${viewport.width}px navbar mobile-menu action`
            )
          } finally {
            await context.close()
          }
        })
      }
    })

    test("foundation targets — shared Select options", async ({ browser }) => {
      for (const viewport of VIEWPORTS) {
        await test.step(`${viewport.width}x${viewport.height}`, async () => {
          const context = await browser.newContext({ baseURL: BASE_URL, viewport })
          const page = await context.newPage()
          try {
            await useMockApi(page, { authenticated: false })
            await gotoWithTransientRetry(page, "/register")
            const trigger = page.locator("#register-role-trigger")
            await expect(trigger).toBeVisible()
            await trigger.click()

            const options = page.getByRole("option")
            await expect(options).toHaveCount(3)
            for (let index = 0; index < 3; index += 1) {
              await assertControlTarget(
                options.nth(index),
                `${viewport.width}px register role option ${index + 1}`
              )
            }
          } finally {
            await context.close()
          }
        })
      }
    })

    test("foundation targets — schedule export menu", async ({ browser }) => {
      for (const viewport of VIEWPORTS) {
        await test.step(`${viewport.width}x${viewport.height}`, async () => {
          const context = await browser.newContext({ baseURL: BASE_URL, viewport })
          const page = await context.newPage()
          try {
            const mock = await useMockApi(page)
            await mock.login(page)
            await gotoWithTransientRetry(page, "/schedule")
            await page
              .locator("#main-content")
              .getByRole("button", { name: /Настройки|Settings/i })
              .click()

            const dialog = page.getByRole("dialog")
            await expect(dialog).toBeVisible()
            const trigger = dialog.getByRole("button", { name: /Экспорт|Export/i })
            await assertControlTarget(trigger, `${viewport.width}px schedule export trigger`)
            await trigger.click()

            const items = dialog.getByRole("menuitem")
            await expect(items).toHaveCount(3)
            for (let index = 0; index < 3; index += 1) {
              await assertControlTarget(
                items.nth(index),
                `${viewport.width}px schedule export option ${index + 1}`
              )
            }
          } finally {
            await context.close()
          }
        })
      }
    })
  })
}
