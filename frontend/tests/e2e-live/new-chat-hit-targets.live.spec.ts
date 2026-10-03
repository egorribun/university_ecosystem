import { expect, loginAs, test } from "./fixtures"

test("NewChat controls meet WCAG target sizes at mobile and desktop widths", async ({
  page,
}, testInfo) => {
  const mobile = testInfo.project.name === "mobile"
  await page.setViewportSize(mobile ? { width: 360, height: 800 } : { width: 1440, height: 900 })
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "teacher")
  await page.goto("/messenger")

  const newChatTrigger = page.getByRole("button", { name: "Новый чат", exact: true })
  await expect(newChatTrigger).toBeVisible()
  await newChatTrigger.click()

  const dialog = page.getByRole("dialog")
  await expect(dialog).toBeVisible()
  const close = dialog.getByRole("button", { name: "Закрыть", exact: true })
  const groupTab = dialog.getByRole("tab", { name: "Группа", exact: true })
  await groupTab.click()
  await expect(groupTab).toHaveAttribute("aria-selected", "true")

  const groupName = dialog.getByRole("textbox", { name: "Название группы", exact: true })
  const search = dialog.getByRole("textbox", { name: "Поиск пользователей", exact: true })
  await expect(groupName).toBeVisible()
  await search.fill("Иван Соколов")

  const member = dialog.getByRole("option").filter({ hasText: "Иван Соколов" })
  await expect(member).toHaveCount(1)
  await member.click()
  await expect(
    dialog.getByRole("button", { name: "Удалить Иван Соколов", exact: true })
  ).toBeVisible()

  // Selecting one member only updates local modal state. The create action stays
  // disabled, so this geometry check performs no chat/group write.
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
})
