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

  // Login lands on the dashboard, which reads the same list without the admin
  // page's no-cache/no-store header. Select that admin request before navigation
  // so a late dashboard response cannot win and a fast admin response is not missed.
  const [response] = await Promise.all([
    page.waitForResponse((response) => {
      const requestUrl = new URL(response.url())
      return (
        requestUrl.pathname === STORY_LIST_PATH &&
        requestUrl.origin === new URL(page.url()).origin &&
        response.request().method() === "GET" &&
        response.request().serviceWorker() === null &&
        !response.request().isNavigationRequest() &&
        response.request().frame() === page.mainFrame() &&
        response.request().headers()["cache-control"] === "no-cache, no-store"
      )
    }),
    page.goto("/admin/stories", { waitUntil: "commit" }),
  ])

  await expect(page).toHaveURL(/\/admin\/stories$/u)
  await expect(
    page.getByRole("heading", { level: 1, name: /Управление сторис|Stories management/u })
  ).toBeVisible()
  await expect(
    page.getByRole("heading", { level: 2, name: /Текущие сторис|Active stories/u })
  ).toBeVisible()

  expect(response.status(), "the admin page loads the real active-story endpoint").toBe(200)
  const stories = (await response.json()) as StorySummary[]
  expect(stories.some((story) => story.title === SEEDED_STORY_TITLE)).toBe(true)
  await expect(
    page.getByRole("heading", { level: 3, name: SEEDED_STORY_TITLE, exact: true })
  ).toBeVisible()
  expect(storyWrites, "opening the admin page must not mutate story records").toEqual([])
})
