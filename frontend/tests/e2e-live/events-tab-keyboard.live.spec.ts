import { expect, loginAs, test } from "./fixtures"

test("Events status tabs are keyboard navigable", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" })
  await loginAs(page, "student")
  await page.goto("/events")
  await expect.poll(() => new URL(page.url()).pathname).toBe("/events")

  const tablist = page.getByRole("tablist", { name: /Мероприятия|Events/u })
  const activeTab = tablist.getByRole("tab", { name: /Актуальные|Upcoming/u })
  const archiveTab = tablist.getByRole("tab", { name: /Прошедшие|Past events/u })
  const myTab = tablist.getByRole("tab", { name: /Мои события|My events/u })
  const tabpanel = page.getByRole("tabpanel")

  await expect(tablist).toBeVisible()
  await expect(tabpanel).toBeVisible()
  await expect(activeTab).toHaveAttribute("aria-selected", "true")
  await expect(activeTab).toHaveAttribute("tabindex", "0")
  await expect(tabpanel).toHaveAttribute("aria-labelledby", "events-tab-active")

  const expectSelection = async (
    selectedKey: "active" | "archive" | "my",
    selectedTab: typeof activeTab
  ) => {
    const tabs = [
      ["active", activeTab],
      ["archive", archiveTab],
      ["my", myTab],
    ] as const

    await expect(selectedTab).toHaveAttribute("aria-selected", "true")
    await expect(selectedTab).toHaveAttribute("tabindex", "0")
    await expect(selectedTab).toBeFocused()
    await expect(tabpanel).toHaveAttribute("aria-labelledby", `events-tab-${selectedKey}`)
    await expect
      .poll(() => new URL(page.url()).searchParams.get("tab"))
      .toBe(selectedKey === "active" ? null : selectedKey)

    for (const [key, tab] of tabs) {
      if (key === selectedKey) continue
      await expect(tab).toHaveAttribute("aria-selected", "false")
      await expect(tab).toHaveAttribute("tabindex", "-1")
    }
  }

  await activeTab.focus()
  await page.keyboard.press("ArrowRight")
  await expectSelection("archive", archiveTab)

  await page.keyboard.press("ArrowRight")
  await expectSelection("my", myTab)

  await page.keyboard.press("ArrowRight")
  await expectSelection("active", activeTab)

  await page.keyboard.press("ArrowLeft")
  await expectSelection("my", myTab)

  await page.keyboard.press("Home")
  await expectSelection("active", activeTab)

  await page.keyboard.press("End")
  await expectSelection("my", myTab)
})
