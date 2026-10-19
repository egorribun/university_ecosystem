import { QueryClient } from "@tanstack/react-query"
import { http, HttpResponse } from "msw"
import { afterEach, beforeEach, describe, expect, it } from "vitest"

import { resetEtagCache } from "@/api/client"
import { fetchStories } from "@/api/stories"
import {
  createDashboardStoriesQueryOptions,
  dashboardStoriesQueryKey,
  prefetchDashboardStories,
  type DashboardStory,
} from "@/hooks/useDashboardStories"
import { acceptBrowserSessionGeneration } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import { testUser } from "@/tests/mocks/handlers"
import { server } from "@/tests/mocks/server"
import type { UserState } from "@/types/Auth"

type ObservedRequest = { method: string; path: string; body: string }
const expectedGet: ObservedRequest = { method: "GET", path: "/api/v1/stories", body: "" }
const observed: ObservedRequest[] = []
const queryClients: QueryClient[] = []
let previousAuthState = useAuthStore.getState()

async function recordRequest(request: Request) {
  observed.push({
    method: request.method,
    path: new URL(request.url).pathname,
    body: await request.clone().text(),
  })
}

function createClient() {
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } })
  queryClients.push(client)
  return client
}

const cachedStory: DashboardStory = {
  id: "44444444-4444-4444-8444-444444444444",
  created_at: "2026-10-01T00:00:00.000Z",
  expires_at: "2026-12-31T23:59:59.000Z",
  is_active: true,
  published_at: "2026-10-01T00:00:00.000Z",
  short_text: "Story cache fixture",
  title: "Campus bulletin",
  cover_url: null,
  cover_url_optimized: null,
  cta_url: null,
}

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
  for (const client of queryClients.splice(0)) client.clear()
  const { user, loading, pendingMfa, authOperation } = previousAuthState
  useAuthStore.setState({ user, loading, pendingMfa, authOperation })
  localStorage.clear()
  acceptBrowserSessionGeneration()
})

async function verifyQueryError() {
  server.use(
    http.get("*/api/v1/stories", async ({ request }) => {
      await recordRequest(request)
      return HttpResponse.json(
        { detail: [{ loc: ["body"], msg: "intentional test rejection", type: "value_error" }] },
        { status: 422 }
      )
    })
  )
  const client = createClient()
  let rejected = false
  let failure: unknown
  try {
    await client.fetchQuery(createDashboardStoriesQueryOptions(client))
  } catch (error) {
    rejected = true
    failure = error
  }

  expect(observed).toEqual([expectedGet])
  expect(rejected).toBe(true)
  expect(failure).toMatchObject({ response: { status: 422 } })
  expect(client.getQueryState(dashboardStoriesQueryKey)?.status).toBe("error")
  expect(client.getQueryData(dashboardStoriesQueryKey)).toBeUndefined()
}

async function verifyNotModified() {
  server.use(
    http.get("*/api/v1/stories", async ({ request }) => {
      await recordRequest(request)
      return new HttpResponse(null, { status: 304 })
    })
  )
  const client = createClient()
  client.setQueryData(dashboardStoriesQueryKey, [cachedStory], { updatedAt: 0 })

  // The query catches request errors and returns cached data. Inspect the direct
  // wrapper response too, so fallback cannot mask accidental rejection of 304.
  const response = await fetchStories()
  expect(observed).toEqual([expectedGet])
  expect(response.status).toBe(304)

  await prefetchDashboardStories(client)

  expect(observed).toEqual([expectedGet, expectedGet])
  const state = client.getQueryState(dashboardStoriesQueryKey)
  expect(state?.status).toBe("success")
  expect(state?.error).toBeNull()
  expect(state?.data).toEqual([cachedStory])
}

describe("dashboard stories generated-client results", () => {
  it("records HTTP 422 as a query error, not an empty successful feed", verifyQueryError)
  it("accepts a real-client 304 and retains the cached story", verifyNotModified)
})
