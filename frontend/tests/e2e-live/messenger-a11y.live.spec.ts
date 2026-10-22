import { expect, loginAs, test } from "./fixtures"

test.use({ trace: "off", screenshot: "off" })

test("Messenger dialog supports keyboard access, restores scroll, and meets hit-target sizes", async ({
  page,
}, testInfo) => {
  const mobile = testInfo.project.name === "mobile"
  await page.setViewportSize(mobile ? { width: 360, height: 800 } : { width: 1440, height: 900 })
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/messenger")

  const newChatTrigger = page.getByRole("button", { name: "Новый чат", exact: true })
  await expect(newChatTrigger).toBeVisible()
  const overflowBeforeDialog = await page
    .locator("body")
    .evaluate((body) => (body as HTMLElement).style.overflow)

  await newChatTrigger.click()
  const dialog = page.getByRole("dialog")
  const close = dialog.getByRole("button", { name: "Закрыть", exact: true })
  let search = dialog.getByRole("textbox", { name: "Поиск пользователей", exact: true })
  await expect(dialog).toBeVisible()
  await expect(dialog).toHaveAttribute("aria-modal", "true")
  await expect(search).toBeFocused()
  await expect
    .poll(() => page.locator("body").evaluate((body) => (body as HTMLElement).style.overflow))
    .toBe("hidden")

  await page.keyboard.press("Tab")
  await expect(close).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(search).toBeFocused()
  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  await expect(newChatTrigger).toBeFocused()
  await expect
    .poll(() => page.locator("body").evaluate((body) => (body as HTMLElement).style.overflow))
    .toBe(overflowBeforeDialog)

  await newChatTrigger.click()
  await expect(dialog).toBeVisible()
  search = dialog.getByRole("textbox", { name: "Поиск пользователей", exact: true })
  const userOptions = dialog
    .getByRole("listbox", { name: "Поиск пользователей" })
    .getByRole("option")
  await search.fill("Synthetic Demo")
  const firstOption = userOptions.first()
  await expect(firstOption).toBeVisible()
  await page.keyboard.press("ArrowDown")
  await expect(firstOption).toBeFocused()
  await expect(firstOption).toHaveAttribute("aria-selected", "false")
  await page.keyboard.press("ArrowUp")
  await expect(search).toBeFocused()
  await expect(page).toHaveURL(/\/messenger$/u)

  await page.keyboard.press("Escape")
  await expect(dialog).toHaveCount(0)
  await newChatTrigger.click()
  await expect(dialog).toBeVisible()

  const groupTab = dialog.getByRole("tab", { name: "Группа", exact: true })
  await groupTab.click()
  await expect(groupTab).toHaveAttribute("aria-selected", "true")
  await expect(dialog.getByRole("textbox", { name: "Название группы", exact: true })).toBeVisible()
  search = dialog.getByRole("textbox", { name: "Поиск пользователей", exact: true })
  await search.fill("Иван Соколов")
  const member = dialog.getByRole("option").filter({ hasText: "Иван Соколов" })
  await expect(member).toHaveCount(1)
  await member.click()
  await expect(
    dialog.getByRole("button", { name: "Удалить Иван Соколов", exact: true })
  ).toBeVisible()

  // Selecting a member only changes modal state. Keep the create action disabled
  // so this audit does not write a group or modify seeded data.
  const groupCreate = dialog.getByRole("button", { name: "Создать группу", exact: true })
  await expect(groupCreate).toBeDisabled()

  const targetSizes = await dialog
    .locator(
      'button, input, textarea, select, a[href], [role="button"], [role="link"], [role="tab"], [role="option"]'
    )
    .evaluateAll((elements) =>
      elements.flatMap((element) => {
        const style = window.getComputedStyle(element)
        if (
          style.display === "none" ||
          style.visibility === "hidden" ||
          element.getClientRects().length === 0
        ) {
          return []
        }

        const rect = element.getBoundingClientRect()
        return [
          {
            kind: element.matches('a[href], [role="link"]') ? "link" : "control",
            width: rect.width,
            height: rect.height,
          },
        ]
      })
    )

  expect(targetSizes.length).toBeGreaterThan(0)
  const undersizedTargets = targetSizes.filter(({ kind, width, height }) =>
    kind === "link" ? height < 24 : width < 44 || height < 44
  )
  expect(
    undersizedTargets,
    "visible controls must be at least 44x44px and text links at least 24px high"
  ).toEqual([])

  await close.click()
  await expect(dialog).toBeHidden()
  await expect
    .poll(() => page.locator("body").evaluate((body) => (body as HTMLElement).style.overflow))
    .toBe(overflowBeforeDialog)
})
