import { expect, loginAs, test } from "./fixtures"

test.use({ trace: "off", screenshot: "off", video: "off" })

test("Settings tabs follow APG keyboard focus, activation, and panel association", async ({
  page,
}) => {
  await loginAs(page, "student")
  await page.goto("/settings")

  const tablist = page.getByRole("tablist", { name: /Разделы настроек|Settings sections/u })
  const tabs = tablist.getByRole("tab")
  const generalTab = tabs.nth(0)
  const accountTab = tabs.nth(1)
  const integrationsTab = tabs.nth(5)
  const panel = page.getByRole("tabpanel")

  await expect(tablist).toBeVisible()
  await expect(tablist).toHaveAttribute("aria-orientation", "horizontal")
  await expect(tabs).toHaveCount(6)
  await expect(panel).toBeVisible()
  await expect(panel).toHaveAttribute("tabindex", "0")

  const panelId = await panel.getAttribute("id")
  expect(panelId).toBeTruthy()
  const tabIds: string[] = []
  for (let tabIndex = 0; tabIndex < 6; tabIndex += 1) {
    const tabId = await tabs.nth(tabIndex).getAttribute("id")
    expect(tabId).toBeTruthy()
    tabIds.push(tabId ?? "")
    await expect(tabs.nth(tabIndex)).toHaveAttribute("aria-controls", panelId ?? "")
  }
  expect(new Set(tabIds).size).toBe(6)

  const expectSelection = async (index: number, url: RegExp) => {
    const selectedTab = tabs.nth(index)
    await expect(selectedTab).toBeVisible()
    await expect(selectedTab).toBeFocused()
    await expect(selectedTab).toHaveAttribute("aria-selected", "true")
    await expect(selectedTab).toHaveAttribute("tabindex", "0")

    const selectedTabId = await selectedTab.getAttribute("id")
    expect(selectedTabId).toBeTruthy()
    await expect(selectedTab).toHaveAttribute("aria-controls", panelId ?? "")
    await expect(panel).toHaveAttribute("aria-labelledby", selectedTabId ?? "")
    await expect(page).toHaveURL(url)

    for (let tabIndex = 0; tabIndex < 6; tabIndex += 1) {
      if (tabIndex === index) continue
      await expect(tabs.nth(tabIndex)).toHaveAttribute("aria-selected", "false")
      await expect(tabs.nth(tabIndex)).toHaveAttribute("tabindex", "-1")
    }
  }

  await expect(generalTab).toHaveAttribute("aria-selected", "true")
  await generalTab.focus()
  await expectSelection(0, /\/settings$/u)

  // Roving tabindex exposes only the selected tab to Tab navigation; the
  // next stop is the associated panel, and Shift+Tab returns to that tab.
  await page.keyboard.press("Tab")
  await expect(panel).toBeFocused()
  await page.keyboard.press("Shift+Tab")
  await expect(generalTab).toBeFocused()

  // End/Home move focus and automatically activate the last/first tab.
  await page.keyboard.press("End")
  await expectSelection(5, /\/settings\?tab=5(?:&|$)/u)
  await expect(integrationsTab).toBeFocused()

  // Arrow keys wrap at both ends and keep URL + tabpanel labeling in sync.
  await page.keyboard.press("ArrowRight")
  await expectSelection(0, /\/settings$/u)
  await page.keyboard.press("ArrowLeft")
  await expectSelection(5, /\/settings\?tab=5(?:&|$)/u)
  await page.keyboard.press("Home")
  await expectSelection(0, /\/settings$/u)

  // Adjacent arrows automatically activate and associate the second tab.
  await page.keyboard.press("ArrowRight")
  await expect(accountTab).toBeFocused()
  await expectSelection(1, /\/settings\?tab=1(?:&|$)/u)
  await page.keyboard.press("ArrowLeft")
  await expectSelection(0, /\/settings$/u)
})
