import { expect, loginAs, test } from "./fixtures"

const STORY_LIST_PATH = "/api/v1/stories"
const SEEDED_STORY_TITLE = "🎓 Сессия: советы по подготовке"

type StorySummary = { title: string }

test("admin can review seeded active stories through the real admin page", async ({ page }) => {
  await loginAs(page, "admin")

  const storyWrites: string[] = []
  page.on("request", (request) => {
    const requestUrl = new URL(request.url())
    if (
      requestUrl.pathname.startsWith(STORY_LIST_PATH) &&
      !["GET", "HEAD"].includes(request.method())
    ) {
      storyWrites.push(`${request.method()} ${requestUrl.pathname}`)
    }
  })

  const storyListResponse = page.waitForResponse((response) => {
    const requestUrl = new URL(response.url())
    return requestUrl.pathname === STORY_LIST_PATH && response.request().method() === "GET"
  })
  await page.goto("/admin/stories")

  await expect(page).toHaveURL(/\/admin\/stories$/u)
  await expect(
    page.getByRole("heading", { level: 1, name: /Управление сторис|Stories management/u })
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { level: 2, name: /Текущие сторис|Active stories/u })
  ).toBeVisible()

  const response = await storyListResponse
  expect(response.status(), "the admin page loads the real active-story endpoint").toBe(200)
  const stories = (await response.json()) as StorySummary[]
  expect(stories.some((story) => story.title === SEEDED_STORY_TITLE)).toBe(true)
  await expect(
    page.getByRole("heading", { level: 3, name: SEEDED_STORY_TITLE, exact: true })
  ).toBeVisible()
  expect(storyWrites, "opening the admin page must not mutate story records").toEqual([])
})
