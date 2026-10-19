import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { resetEtagCache } from "@/api/client"
import { deleteNews } from "@/api/news"
import {
  clearNotifications,
  markAllNotificationsRead,
  markNotificationRead,
} from "@/api/notifications"
import { createStory, deleteStory, updateStory } from "@/api/stories"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import type { UserState } from "@/types/Auth"

type ExpectedRequest = {
  method: string
  path: string
  body: unknown
}

type MutationCase = ExpectedRequest & {
  name: string
  run: () => Promise<unknown>
}

const newsId = "11111111-1111-4111-8111-111111111111"
const storyId = "22222222-2222-4222-8222-222222222222"
const notificationId = "33333333-3333-4333-8333-333333333333"

const cases: MutationCase[] = [
  {
    name: "delete news",
    method: "DELETE",
    path: `/api/v1/news/${newsId}`,
    body: null,
    run: () => deleteNews(newsId),
  },
  {
    name: "create story",
    method: "POST",
    path: "/api/v1/stories",
    body: { title: "Campus bulletin", short_text: "Library hours update" },
    run: () => createStory({ title: "Campus bulletin", short_text: "Library hours update" }),
  },
  {
    name: "update story",
    method: "PATCH",
    path: `/api/v1/stories/${storyId}`,
    body: { is_active: false },
    run: () => updateStory(storyId, { is_active: false }),
  },
  {
    name: "delete story",
    method: "DELETE",
    path: `/api/v1/stories/${storyId}`,
    body: null,
    run: () => deleteStory(storyId),
  },
  {
    name: "mark one notification read",
    method: "PATCH",
    path: `/api/v1/notifications/${notificationId}/read`,
    body: null,
    run: () => markNotificationRead(notificationId),
  },
  {
    name: "mark all notifications read",
    method: "POST",
    path: "/api/v1/notifications/read-all",
    body: null,
    run: () => markAllNotificationsRead(),
  },
  {
    name: "clear notifications",
    method: "DELETE",
    path: "/api/v1/notifications",
    body: null,
    run: () => clearNotifications(),
  },
]

const observed: ExpectedRequest[] = []
let previousAuthState = useAuthStore.getState()

beforeEach(() => {
  previousAuthState = useAuthStore.getState()
  observed.length = 0
  localStorage.clear()
  acceptBrowserSessionGeneration()
  useAuthStore.setState({
    user: { ...testUser } as UserState,
    loading: false,
    pendingMfa: null,
    authOperation: false,
  })
})

afterEach(() => {
  server.resetHandlers()
  resetEtagCache()
  const { user, loading, pendingMfa, authOperation } = previousAuthState
  useAuthStore.setState({ user, loading, pendingMfa, authOperation })
  localStorage.clear()
  acceptBrowserSessionGeneration()
})

async function verifyRejectedMutation(operation: MutationCase) {
  server.use(
    http.all(`*${operation.path}`, async ({ request }) => {
      const rawBody = await request.clone().text()
      observed.push({
        method: request.method,
        path: new URL(request.url).pathname,
        body: rawBody ? (JSON.parse(rawBody) as unknown) : null,
      })
      return HttpResponse.json(
        { detail: [{ loc: ["body"], msg: "intentional test rejection", type: "value_error" }] },
        { status: 422 }
      )
    })
  )

  let rejected = false
  let failure: unknown
  try {
    await operation.run()
  } catch (error) {
    rejected = true
    failure = error
  }

  // Prove the request reached the real HTTP boundary before testing rejection.
  expect(observed).toEqual([
    { method: operation.method, path: operation.path, body: operation.body },
  ])
  expect(rejected).toBe(true)
  expect(failure).toMatchObject({ response: { status: 422 } })
}

describe("generated-client mutation HTTP failures", () => {
  it.each(cases)("$name sends its exact request and rejects HTTP 422", verifyRejectedMutation)
})
