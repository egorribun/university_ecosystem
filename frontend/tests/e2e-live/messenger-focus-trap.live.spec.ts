import { expect, loginAs, test } from "./fixtures"

test("Tab and Shift+Tab keep focus inside the read-only new-chat dialog", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/messenger")

  const newChatTrigger = page.getByRole("button", { name: "Новый чат", exact: true })
  await expect(newChatTrigger).toBeVisible()
  await newChatTrigger.click()

  const dialog = page.getByRole("dialog")
  const search = dialog.getByRole("textbox", { name: "Поиск пользователей", exact: true })
  const close = dialog.getByRole("button", { name: "Закрыть", exact: true })

  await expect(dialog).toBeVisible()
  await expect(search).toBeFocused()

  // Search is the last tab stop in the empty dialog; forward and reverse tabbing
  // must wrap to the other end of the focus sequence instead of escaping it.
  await page.keyboard.press("Tab")
  await expect(close).toBeFocused()

  await page.keyboard.press("Shift+Tab")
  await expect(search).toBeFocused()
})
