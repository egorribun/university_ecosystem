import { test, type Page } from "./test"
import { useMockApi as setupMockApi } from "./utils/mockApi"
import { gotoWithTransientRetry } from "./utils/navigation"
import {
  expectEmptySearchResults,
  expectHighlightedSearchResults,
  expectRelevantSearchResults,
  installSearchReadinessProbe,
} from "./utils/searchFullText"

async function prepareSearch(page: Page): Promise<void> {
  await installSearchReadinessProbe(page)
  const { login } = await setupMockApi(page)
  await login(page)
  await gotoWithTransientRetry(page, "/dashboard", { waitUntil: "domcontentloaded" })
}

test.describe("Full-text search", () => {
  test.use({ serviceWorkers: "block" })

  test("search query returns a list of relevant results", async ({ page }) => {
    await prepareSearch(page)
    await expectRelevantSearchResults(page)
  })

  test("matched terms are highlighted in search results", async ({ page }) => {
    await prepareSearch(page)
    await expectHighlightedSearchResults(page)
  })

  test("shows no-results message when query matches nothing", async ({ page }) => {
    await prepareSearch(page)
    await expectEmptySearchResults(page)
  })
})
