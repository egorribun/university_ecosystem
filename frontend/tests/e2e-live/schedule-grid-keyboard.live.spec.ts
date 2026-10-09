import { expect, loginAs, test } from "./fixtures"

test.use({ trace: "off", screenshot: "off", video: "off" })

test("Enter opens the lesson in the keyboard-selected schedule grid cell", async ({
  page,
}, testInfo) => {
  test.skip(testInfo.project.name !== "desktop", "The desktop schedule uses the keyboard grid")

  await loginAs(page, "student")
  await page.goto("/schedule")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/schedule")

  const grid = page.getByRole("grid", { name: /^(?:Расписание|Schedule)$/u })
  await expect(grid).toBeVisible()

  const lessonCard = grid.locator('[id^="lesson-card-"]').first()
  await expect(lessonCard).toBeVisible()

  const cell = lessonCard.locator("xpath=..")
  const cellId = await cell.getAttribute("id")
  const position = cellId?.match(/^sched-cell-(\d+)-(\d+)$/u)
  expect(position).not.toBeNull()

  // ArrowLeft clamps the initial position to row 0, column 0 and focuses that
  // grid cell. The following arrows walk to the first real seeded lesson.
  await page.keyboard.press("ArrowLeft")
  for (let row = 0; row < Number(position?.[1]); row += 1) {
    await page.keyboard.press("ArrowDown")
  }
  for (let col = 0; col < Number(position?.[2]); col += 1) {
    await page.keyboard.press("ArrowRight")
  }
  await expect(cell).toBeFocused()
  await page.keyboard.press("Enter")

  const detailsDialog = page.getByRole("dialog")
  await expect(detailsDialog).toBeVisible()
  await expect(detailsDialog).toContainText(await lessonCard.locator("h3").innerText())
  await expect
    .poll(() => detailsDialog.evaluate((dialog) => dialog.contains(document.activeElement)))
    .toBe(true)

  await page.keyboard.press("Escape")
  await expect(detailsDialog).toBeHidden()
  await expect(cell).toBeFocused()
})
