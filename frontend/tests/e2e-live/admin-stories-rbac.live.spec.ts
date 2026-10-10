import { randomUUID } from "node:crypto"
import type { BrowserContext, Page } from "@playwright/test"
import { expect, loginAs, test } from "./fixtures"

interface StoryRow {
  id: string
  title: string
  short_text: string
}

const readCsrfToken = (page: Page): Promise<string> =>
  page.evaluate(() => {
    const cookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    return cookie ? decodeURIComponent(cookie.slice("csrf_token=".length)) : ""
  })

const deleteStoryByExactId = async (adminPage: Page, storyId: string): Promise<void> => {
  const result = await adminPage.evaluate(async (id) => {
    const csrfCookie = document.cookie
      .split(";")
      .map((part) => part.trim())
      .find((part) => part.startsWith("csrf_token="))
    if (!csrfCookie) return { status: 0, ok: false }

    const csrfToken = decodeURIComponent(csrfCookie.slice("csrf_token=".length))
    const response = await fetch(`/api/v1/stories/${encodeURIComponent(id)}`, {
      method: "DELETE",
      credentials: "same-origin",
      headers: { "X-CSRF-Token": csrfToken },
    })
    const body = (await response.json().catch(() => null)) as { ok?: boolean } | null
    return { status: response.status, ok: body?.ok === true }
  }, storyId)
  if (result.status === 404) return
  expect(result.status, "admin cleanup deletes only the exact test-owned story").toBe(200)
  expect(result.ok).toBe(true)
}

const cleanupCreatedStory = async (
  adminPage: Page,
  title: string,
  shortText: string,
  createdStoryId: string | null
): Promise<void> => {
  const searchKey = randomUUID()
  const response = await adminPage.request.get(`/api/v1/stories?__live_cleanup=${searchKey}`)
  expect(response.status(), "admin cleanup can inspect the public story collection").toBe(200)
  const stories = (await response.json()) as StoryRow[]

  if (createdStoryId) {
    const byId = stories.filter((entry) => entry.id === createdStoryId)
    if (byId.length === 0) return
    const ownedStory = byId[0]
    if (
      byId.length !== 1 ||
      !ownedStory ||
      ownedStory.title !== title ||
      ownedStory.short_text !== shortText
    ) {
      throw new Error(
        "refusing cleanup because the returned story id is not the exact test-owned record"
      )
    }
    await deleteStoryByExactId(adminPage, createdStoryId)
    return
  }

  const matches = stories.filter((entry) => entry.title === title && entry.short_text === shortText)
  if (matches.length === 0) return
  if (matches.length !== 1) {
    throw new Error("refusing cleanup because the exact synthetic story match is ambiguous")
  }
  const match = matches[0]
  if (!match) throw new Error("refusing cleanup because the exact synthetic story is missing")
  await deleteStoryByExactId(adminPage, match.id)
}

for (const role of ["student", "teacher"] as const) {
  test(`${role} cannot open story administration or mutate stories`, async ({ page, browser }) => {
    const identity = randomUUID()
    const ownedTitle = `Live RBAC admin-owned story ${role} ${identity}`
    const ownedShortText = `live-rbac-admin-owned-${identity}`
    const attemptedTitle = `Live RBAC unauthorized story ${role} ${identity}`
    const attemptedShortText = `live-rbac-unauthorized-${identity}`
    let adminContext: BrowserContext | null = null
    let adminPage: Page | null = null
    let ownedCreateMayHaveSucceeded = false
    let ownedStoryId: string | null = null
    let unauthorizedCreateMayHaveSucceeded = false
    let unauthorizedStoryId: string | null = null
    let testFailure: unknown
    let testFailed = false

    try {
      adminContext = await browser.newContext({
        baseURL: process.env.LIVE_BASE_URL,
        ignoreHTTPSErrors: true,
        locale: "ru-RU",
      })
      adminPage = await adminContext.newPage()
      await loginAs(adminPage, "admin")
      await loginAs(page, role)

      const adminIdentityResponse = await adminPage.request.get("/api/v1/users/me")
      expect(adminIdentityResponse.status(), "admin fixture must be authenticated").toBe(200)
      expect((await adminIdentityResponse.json()).role, "story owner fixture role").toBe("admin")

      const adminCsrfToken = await readCsrfToken(adminPage)
      expect(adminCsrfToken, "admin has CSRF proof for test-owned story creation").not.toBe("")

      await adminPage.goto("/admin/stories")
      await expect(adminPage).toHaveURL(/\/admin\/stories$/u)
      await expect(
        adminPage.getByRole("heading", {
          level: 1,
          name: /Stories management|Управление сторис/u,
        })
      ).toBeVisible()

      const publishedAt = new Date(Date.now() - 60_000).toISOString()
      const expiresAt = new Date(Date.now() + 86_400_000).toISOString()
      ownedCreateMayHaveSucceeded = true
      const adminCreateResponse = await adminPage.evaluate(
        async ({ payload, csrfToken }) => {
          const response = await fetch("/api/v1/stories", {
            method: "POST",
            credentials: "same-origin",
            headers: {
              "Content-Type": "application/json",
              "X-CSRF-Token": csrfToken,
            },
            body: JSON.stringify(payload),
          })
          return {
            status: response.status,
            body: await response.json().catch(() => null),
          }
        },
        {
          payload: {
            title: ownedTitle,
            title_en: ownedTitle,
            short_text: ownedShortText,
            short_text_en: ownedShortText,
            published_at: publishedAt,
            expires_at: expiresAt,
            is_active: true,
          },
          csrfToken: adminCsrfToken,
        }
      )
      expect(
        adminCreateResponse.status,
        "admin creates the temporary story through the real API"
      ).toBe(200)
      const createdBody = adminCreateResponse.body as Partial<StoryRow>
      expect(createdBody.title).toBe(ownedTitle)
      expect(createdBody.short_text).toBe(ownedShortText)
      if (typeof createdBody.id !== "string" || createdBody.id.length === 0) {
        throw new Error("admin story create response did not include a usable story id")
      }
      ownedStoryId = createdBody.id
      await adminPage.reload()
      await expect(adminPage).toHaveURL(/\/admin\/stories$/u)
      await expect(adminPage.getByText(ownedTitle, { exact: true })).toBeVisible()

      const identityResponse = await page.request.get("/api/v1/users/me")
      expect(identityResponse.status(), `${role} fixture must be authenticated`).toBe(200)
      expect((await identityResponse.json()).role, `${role} fixture role`).toBe(role)

      await page.goto("/admin/stories")
      await expect(page, `${role} should be redirected from story administration`).toHaveURL(
        /\/dashboard$/u
      )
      await expect(
        page.getByRole("heading", {
          level: 1,
          name: /Stories management|Управление сторис/u,
        })
      ).toHaveCount(0)

      const csrfToken = await readCsrfToken(page)
      expect(csrfToken, "the authenticated role has CSRF proof for real API attempts").not.toBe("")

      unauthorizedCreateMayHaveSucceeded = true
      const response = await page.request.post("/api/v1/stories", {
        data: {
          title: attemptedTitle,
          title_en: attemptedTitle,
          short_text: attemptedShortText,
          short_text_en: attemptedShortText,
          published_at: publishedAt,
          expires_at: expiresAt,
          is_active: true,
        },
        headers: { "X-CSRF-Token": csrfToken },
      })
      unauthorizedCreateMayHaveSucceeded = response.ok() || response.status() >= 500
      if (response.ok()) {
        const body = (await response.json()) as { id?: unknown }
        if (typeof body.id === "string") unauthorizedStoryId = body.id
      }
      expect(response.status(), `${role} POST /api/v1/stories must be forbidden`).toBe(403)

      const deleteResponse = await page.request.delete(
        `/api/v1/stories/${encodeURIComponent(createdBody.id)}`,
        { headers: { "X-CSRF-Token": csrfToken } }
      )
      expect(deleteResponse.status(), `${role} DELETE /api/v1/stories must be forbidden`).toBe(403)

      const adminStoriesResponse = await adminPage.request.get(
        `/api/v1/stories?__live_verify=${randomUUID()}`
      )
      expect(adminStoriesResponse.status(), "admin can confirm the story remains present").toBe(200)
      const adminStories = (await adminStoriesResponse.json()) as StoryRow[]
      const ownedStory = adminStories.find((entry) => entry.id === createdBody.id)
      expect(
        ownedStory,
        "forbidden student/teacher DELETE must leave the story intact"
      ).toBeDefined()
      expect(ownedStory?.title).toBe(ownedTitle)
      expect(ownedStory?.short_text).toBe(ownedShortText)

      const nonExistentStoryId = randomUUID()
      const updateResponse = await page.request.patch(`/api/v1/stories/${nonExistentStoryId}`, {
        data: { title: `Unauthorized story update ${identity}` },
        headers: { "X-CSRF-Token": csrfToken },
      })
      expect(updateResponse.status(), `${role} PATCH /api/v1/stories must be forbidden`).toBe(403)
    } catch (error) {
      testFailure = error
      testFailed = true
    }

    const cleanupErrors: unknown[] = []
    if (ownedCreateMayHaveSucceeded && adminPage) {
      try {
        await cleanupCreatedStory(adminPage, ownedTitle, ownedShortText, ownedStoryId)
      } catch (error) {
        cleanupErrors.push(error)
      }
    }
    if (unauthorizedCreateMayHaveSucceeded && adminPage) {
      try {
        await cleanupCreatedStory(
          adminPage,
          attemptedTitle,
          attemptedShortText,
          unauthorizedStoryId
        )
      } catch (error) {
        cleanupErrors.push(error)
      }
    }
    if (adminContext) {
      try {
        await adminContext.close()
      } catch (error) {
        cleanupErrors.push(error)
      }
    }

    if (testFailed && cleanupErrors.length > 0) {
      throw new AggregateError(
        [testFailure, ...cleanupErrors],
        "admin-stories RBAC assertion and test-story cleanup both failed"
      )
    }
    if (testFailed) throw testFailure
    if (cleanupErrors.length > 0) {
      throw new AggregateError(cleanupErrors, "test-owned story cleanup failed")
    }
  })
}
