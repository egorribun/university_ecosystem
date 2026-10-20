import { expect, type Locator, type Page, type Route } from "@playwright/test"

const HIGHLIGHT_OPEN = "\u0000MARK_OPEN\u0000"
const HIGHLIGHT_CLOSE = "\u0000MARK_CLOSE\u0000"

export async function installSearchReadinessProbe(page: Page): Promise<void> {
  await page.addInitScript(() => {
    const state = window as Window & { __ueDeferredOverlaysReady?: boolean }
    state.__ueDeferredOverlaysReady = false
    window.addEventListener(
      "ue:deferred-global-overlays-ready",
      () => {
        state.__ueDeferredOverlaysReady = true
      },
      { once: true }
    )
  })
}

function searchPayload(query: string, empty: boolean) {
  return {
    query,
    results: {
      news: empty
        ? []
        : [
            {
              id: "result-1",
              type: "news",
              title: "University research breakthrough",
              summary:
                "Scientists at the university achieved a major " +
                HIGHLIGHT_OPEN +
                "research" +
                HIGHLIGHT_CLOSE +
                " breakthrough.",
              url: "/news/1",
              score: 0.95,
            },
          ],
      events: empty
        ? []
        : [
            {
              id: "result-2",
              type: "events",
              title: "Annual research conference",
              summary:
                "Join us for the annual " +
                HIGHLIGHT_OPEN +
                "research" +
                HIGHLIGHT_CLOSE +
                " conference on campus.",
              url: "/events/2",
              score: 0.88,
            },
          ],
    },
  }
}

async function withControlledSearch(
  page: Page,
  empty: boolean,
  check: (dialog: Locator) => Promise<void>
): Promise<void> {
  const query = empty ? "zzznoresultsquery" : "research"
  const payload = searchPayload(query, empty)
  const matchesSearch = (url: URL) => url.pathname === "/api/v1/search"
  const handler = async (route: Route) => {
    if (route.request().method() !== "GET") {
      await route.fallback()
      return
    }
    const requestUrl = new URL(route.request().url())
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify(searchPayload(requestUrl.searchParams.get("q") ?? "", empty)),
    })
  }

  // Install after any blanket mock-API setup; remove this exact handler afterward.
  await page.route(matchesSearch, handler)
  try {
    await page.waitForFunction(() => {
      const state = window as Window & { __ueDeferredOverlaysReady?: boolean }
      return state.__ueDeferredOverlaysReady === true
    })
    await page.keyboard.press("Control+k")
    const dialog = page.getByRole("dialog", { name: /^(Search|Поиск)$/u })
    const input = dialog.getByRole("textbox", {
      name: /^(Search the application|Поиск по приложению)$/u,
    })
    await expect(dialog).toBeVisible()
    await expect(input).toBeVisible()
    await expect(input).toBeFocused()

    const [response] = await Promise.all([
      page.waitForResponse((candidate) => {
        const url = new URL(candidate.url())
        return (
          matchesSearch(url) &&
          candidate.request().method() === "GET" &&
          url.searchParams.get("q") === query
        )
      }),
      input.fill(query),
    ])
    expect(response.status()).toBe(200)
    expect(await response.json()).toEqual(payload)
    await check(dialog)
  } finally {
    await page.unroute(matchesSearch, handler)
  }
}

async function requireRelevantResults(dialog: Locator): Promise<Locator> {
  const results = dialog.locator("button[data-search-item]")
  await expect(results).toHaveCount(2)
  await expect(results.nth(0)).toBeVisible()
  await expect(results.nth(1)).toBeVisible()
  await expect(
    results.nth(0).getByText("University research breakthrough", { exact: true })
  ).toBeVisible()
  await expect(
    results.nth(1).getByText("Annual research conference", { exact: true })
  ).toBeVisible()
  return results
}

export async function expectRelevantSearchResults(page: Page): Promise<void> {
  await withControlledSearch(page, false, async (dialog) => {
    await requireRelevantResults(dialog)
  })
}

export async function expectHighlightedSearchResults(page: Page): Promise<void> {
  await withControlledSearch(page, false, async (dialog) => {
    const results = await requireRelevantResults(dialog)
    for (const result of [results.nth(0), results.nth(1)]) {
      const highlight = result.locator("mark")
      await expect(highlight).toHaveCount(1)
      await expect(highlight).toHaveText("research")
      await expect(highlight).toBeVisible()
    }
  })
}

export async function expectEmptySearchResults(page: Page): Promise<void> {
  await withControlledSearch(page, true, async (dialog) => {
    await expect(dialog.getByText(/^(No matching results|Совпадений не найдено)$/u)).toBeVisible()
    await expect(dialog.locator("button[data-search-item]")).toHaveCount(0)
  })
}
