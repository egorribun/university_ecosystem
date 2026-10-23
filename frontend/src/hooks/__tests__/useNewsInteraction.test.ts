/**
 * Session 11 coverage: src/hooks/useNewsInteraction.ts
 *
 * like/comment/edit/delete optimistic mutations + offline IndexedDB queue.
 *
 * Gated mutation/refetch responses prove optimistic state and rollback before
 * server data can hide either regression. The remaining tests use a stateful
 * MSW server simulation: the hook runs `onMutate` (optimistic) then
 * `onSettled` (invalidateQueries → refetch). A *static* GET body would silently
 * revert every optimistic update on that refetch, so handlers here keep a mutable
 * `state` that the POST/PATCH/DELETE mutate on success — the refetch then CONFIRMS
 * the optimistic change (deterministic, no waitFor race). For the offline path the
 * GET *also* errors when `navigator.onLine === false`, mirroring a real offline
 * refetch (React Query keeps the last/optimistic data instead of reverting).
 *
 * MSW v3 intercepts the raw axios instance (`@/api/client`) on relative `/news/...`
 * paths (NOT `/api/...` → setupTests' contract validator skips them). useAuth is
 * mocked via a hoisted holder so `user` is controllable without a provider.
 * Offline = `navigator.onLine = false`; the SW-sync block is skipped (jsdom has no
 * `serviceWorker`/`SyncManager`), so the IDB queue write succeeds silently.
 */
import { act, cleanup, renderHook, waitFor } from "@testing-library/react"
import {
  QueryClient,
  QueryClientProvider,
  notifyManager,
  type InfiniteData,
} from "@tanstack/react-query"
import { IDBFactory } from "fake-indexeddb"
import { http, HttpResponse } from "msw"
import { createElement, type PropsWithChildren } from "react"
import { afterAll, afterEach, beforeAll, beforeEach, describe, expect, it, vi } from "vitest"

import { server } from "@/tests/mocks/server"
import { NOTIFICATION_INTERACTIONS_DB_VERSION } from "@/constants/notificationInteractionsDb"
import { withExpectedConsole } from "@/tests/strictConsole"
import type { User } from "@/types/User"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import api from "@/api/client"
import {
  NEWS_COMMENTS_PAGE_SIZE,
  useNewsInteraction,
  type NewsComment,
  type NewsInteractions,
} from "../useNewsInteraction"

const authMock = vi.hoisted(() => ({ user: null as User | null }))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: authMock.user }) }))

const NEWS_ID = "00000000-0000-0000-0000-000000000001"
const SIGNED_IN_USER_ID = "11111111-1111-4111-8111-111111111111"
const EXISTING_COMMENT_AUTHOR_ID = "22222222-2222-4222-8222-222222222222"
const PUBLIC_COMMENT_AUTHOR_ID = "33333333-3333-4333-8333-333333333333"
const STORE = "pending-news-interactions"
const DB_NAME = "notification-interactions"
const DB_VERSION = NOTIFICATION_INTERACTIONS_DB_VERSION

const commentFixtureId = (sequence: number) =>
  `00000000-0000-4000-8000-${sequence.toString(16).padStart(12, "0")}`

const baseInteractions: NewsInteractions = {
  likes_count: 3,
  is_liked: false,
  comments: [],
  comments_count: 0,
}

function makeWrapper() {
  const qc = new QueryClient({
    defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
  })
  const wrapper = ({ children }: PropsWithChildren) =>
    createElement(QueryClientProvider, { client: qc }, children)
  return { qc, wrapper }
}

function setOnline(value: boolean) {
  Object.defineProperty(navigator, "onLine", { configurable: true, value })
}

function setAuthFixture(user: User | null, loading = false) {
  authMock.user = user
  useAuthStore.setState({ user: user as UserState | null, loading })
}

/** The cache stores paged data; flatten it the way the hook's select does. */
function cachedInteractions(qc: QueryClient): NewsInteractions | undefined {
  const data = qc.getQueryData<InfiniteData<NewsInteractions, number>>([
    "news",
    NEWS_ID,
    "interactions",
  ])
  const first = data?.pages[0]
  if (!data || !first) return undefined
  return { ...first, comments: data.pages.flatMap((page) => page.comments) }
}

function deferred<T>() {
  let resolve!: (value: T) => void
  const promise = new Promise<T>((res) => {
    resolve = res
  })
  return { promise, resolve }
}

type MutationSettlement<T> =
  { status: "fulfilled"; value: T } | { status: "rejected"; reason: unknown }

function observeMutation<T>(promise: Promise<T>): Promise<MutationSettlement<T>> {
  return promise.then(
    (value) => ({ status: "fulfilled", value }),
    (reason: unknown) => ({ status: "rejected", reason })
  )
}

async function startMutation<T>(start: () => Promise<T>) {
  let settlement!: Promise<MutationSettlement<T>>
  await act(async () => {
    settlement = observeMutation(start())
    await Promise.resolve()
  })
  return { settlement }
}

function holdInteractionResponses(action: "like" | "comment", initial: NewsInteractions) {
  const mutation = deferred<Response>()
  const refetch = deferred<NewsInteractions>()
  const request = { started: false }
  let hasLoaded = false
  server.use(
    http.get(`*/news/${NEWS_ID}/interactions`, async () => {
      if (!hasLoaded) {
        hasLoaded = true
        return HttpResponse.json(initial)
      }
      return HttpResponse.json(await refetch.promise)
    }),
    http.post(`*/news/${NEWS_ID}/${action}`, () => {
      request.started = true
      return mutation.promise
    })
  )
  return { mutation, refetch, request }
}

async function waitForMutationAttempt(qc: QueryClient, request: { started: boolean }) {
  // The request starts after onMutate finishes. Also stop waiting if setup
  // fails, so the pending-state assertion reports that failure directly.
  await waitFor(() => {
    const failed = qc
      .getMutationCache()
      .getAll()
      .some((mutation) => mutation.state.status === "error")
    expect(request.started || failed).toBe(true)
  })
}

type Behavior = "ok" | "500" | "401" | "offline"

/**
 * Register stateful handlers for one test. `state` is the simulated server truth:
 * the GET returns it (or network-errors when offline), and each `"ok"` mutation
 * mutates it so the post-mutation refetch confirms the optimistic update.
 */
function setupServer(opts: {
  initial: NewsInteractions
  like?: Behavior
  comment?: Behavior
  patch?: Behavior
  del?: Behavior
}): NewsInteractions {
  // structuredClone-equivalent; note JSON drops `comments_count: undefined` keys,
  // which is exactly the "undefined → fall back to comments.length" branch we want.
  const state: NewsInteractions = JSON.parse(JSON.stringify(opts.initial))

  const errResp = (b: Behavior | undefined) => {
    if (b === "500") return new HttpResponse(null, { status: 500 })
    if (b === "401") return HttpResponse.json({ detail: "x" }, { status: 401 })
    if (b === "offline") return HttpResponse.error()
    return null
  }

  const handlers = [
    http.get("*/news/:newsId/interactions", () =>
      navigator.onLine ? HttpResponse.json(state) : HttpResponse.error()
    ),
    http.get("*/api/v1/news/:newsId/interactions", () =>
      navigator.onLine ? HttpResponse.json(state) : HttpResponse.error()
    ),
  ]

  if (opts.like) {
    handlers.push(
      http.post("*/news/:newsId/like", () => {
        const e = errResp(opts.like)
        if (e) return e
        state.is_liked = !state.is_liked
        state.likes_count = state.is_liked ? state.likes_count + 1 : state.likes_count - 1
        return new HttpResponse(null, { status: 200 })
      })
    )
  }

  if (opts.comment) {
    handlers.push(
      http.post("*/news/:newsId/comment", async ({ request }) => {
        const e = errResp(opts.comment)
        if (e) return e
        const body = (await request.json()) as { content: string }
        const created: NewsComment = {
          id: commentFixtureId(1000 + state.comments.length),
          content: body.content,
          user_id: authMock.user?.id ?? PUBLIC_COMMENT_AUTHOR_ID,
          user_name: authMock.user?.full_name ?? "You",
          created_at: "2026-06-13T00:00:00Z",
        }
        state.comments = [...state.comments, created]
        state.comments_count = state.comments.length
        return HttpResponse.json(created)
      })
    )
  }

  if (opts.patch) {
    handlers.push(
      http.patch("*/news/comments/:commentId", async ({ request, params }) => {
        const e = errResp(opts.patch)
        if (e) return e
        const body = (await request.json()) as { content: string }
        state.comments = state.comments.map((c) =>
          c.id === params.commentId ? { ...c, content: body.content } : c
        )
        return HttpResponse.json({ id: params.commentId, content: body.content })
      })
    )
  }

  if (opts.del) {
    handlers.push(
      http.delete("*/news/comments/:commentId", ({ params }) => {
        const e = errResp(opts.del)
        if (e) return e
        state.comments = state.comments.filter((c) => c.id !== params.commentId)
        state.comments_count = state.comments.length
        return new HttpResponse(null, { status: 204 })
      })
    )
  }

  server.use(...handlers)
  return state
}

type QueueEntry = { url: string; payload: unknown; method: string; timestamp: number }

/** Creates the stores exactly as the service worker's upgrade does (src/sw/offline.ts). */
function createWorkerStores(db: IDBDatabase) {
  db.createObjectStore("pending-navigations", { keyPath: "id", autoIncrement: true })
  db.createObjectStore("pending-reports", { keyPath: "id", autoIncrement: true }).createIndex(
    "dedupeKey",
    "dedupeKey",
    { unique: false }
  )
  db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true })
  const mutations = db.createObjectStore("pending-mutations", {
    keyPath: "id",
    autoIncrement: true,
  })
  mutations.createIndex("mutationId", "mutationId", { unique: true })
  mutations.createIndex("category", "category", { unique: false })
  mutations.createIndex("dedupeKey", "dedupeKey", { unique: false })
}

function openDatabaseAt(version: number, onUpgrade?: (db: IDBDatabase) => void) {
  return new Promise<IDBDatabase>((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, version)
    req.onupgradeneeded = () => onUpgrade?.(req.result)
    req.onsuccess = () => resolve(req.result)
    req.onerror = () => reject(req.error)
  })
}

/** Opens the database at the service worker's version, as the worker does on its first run. */
function openServiceWorkerSchema(): Promise<IDBDatabase> {
  return openDatabaseAt(DB_VERSION, createWorkerStores)
}

function readQueue(): Promise<QueueEntry[]> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(DB_NAME, DB_VERSION)
    req.onupgradeneeded = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE))
        db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true })
    }
    req.onsuccess = () => {
      const db = req.result
      if (!db.objectStoreNames.contains(STORE)) {
        resolve([])
        return
      }
      const tx = db.transaction(STORE, "readonly")
      const all = tx.objectStore(STORE).getAll()
      all.onsuccess = () => resolve(all.result as QueueEntry[])
      all.onerror = () => reject(all.error)
    }
    req.onerror = () => reject(req.error)
  })
}

function precreateQueueDatabase(): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(DB_NAME, 1)
    request.onupgradeneeded = () => {
      const db = request.result
      db.createObjectStore("pending-navigations", { keyPath: "id", autoIncrement: true })
      db.createObjectStore("pending-reports", { keyPath: "id", autoIncrement: true })
      db.createObjectStore(STORE, { keyPath: "id", autoIncrement: true })
    }
    request.onsuccess = () => {
      request.result.close()
      resolve()
    }
    request.onerror = () => reject(request.error)
  })
}

beforeAll(() => {
  // React Query schedules observer notifications after the mutation's async
  // work. Keep those real hook state transitions inside React's act scope so
  // strictConsole reports only application diagnostics.
  notifyManager.setNotifyFunction((callback) => {
    act(callback)
  })
})

afterAll(() => {
  notifyManager.setNotifyFunction((callback) => callback())
})

beforeEach(() => {
  // Fresh fake-indexeddb factory per test. The queue helper closes its own
  // connection, but readQueue() intentionally leaves a read-only handle open
  // for assertions; replacing the factory drops all test-only handles + DBs
  // atomically and prevents a later deleteDatabase/open pair from blocking.
  globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
  setOnline(true)
  setAuthFixture({ id: SIGNED_IN_USER_ID, full_name: "Test User" } as User)
})

afterEach(() => {
  setOnline(true)
  cleanup()
  setAuthFixture(null, true)
})

describe("useNewsInteraction — query", () => {
  it("loads interactions via GET", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.interactions).toEqual(baseInteractions)
  })

  it("initialData seeds immediately (all defaulting branches)", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions })
    const { result } = renderHook(
      () => useNewsInteraction(NEWS_ID, { initialData: { likes_count: 9, is_liked: true } }),
      { wrapper }
    )
    expect(result.current.interactions?.likes_count).toBe(9)
    expect(result.current.interactions?.is_liked).toBe(true)
    expect(result.current.interactions?.comments).toEqual([])
    expect(result.current.interactions?.comments_count).toBe(0)
    // The seeded summary is stale, so the comment request runs; let it settle.
    await waitFor(() => expect(qc.isFetching()).toBe(0))
  })

  it("fetches the comment list on mount even when the summary was seeded", async () => {
    const { wrapper } = makeWrapper()
    const comment: NewsComment = {
      id: commentFixtureId(1),
      content: "Loaded from the server",
      user_id: EXISTING_COMMENT_AUTHOR_ID,
      user_name: "Ann",
      created_at: "2026-06-13T00:00:00Z",
    }
    setupServer({ initial: { ...baseInteractions, comments: [comment], comments_count: 1 } })

    const { result } = renderHook(
      () => useNewsInteraction(NEWS_ID, { initialData: { likes_count: 3, comments_count: 1 } }),
      { wrapper }
    )

    await waitFor(() => expect(result.current.interactions?.comments).toEqual([comment]))
  })

  it("keeps a summary-only entry without requesting the comment list", async () => {
    const { wrapper } = makeWrapper()
    let commentRequests = 0
    server.use(
      http.get("*/news/:newsId/interactions", () => {
        commentRequests += 1
        return HttpResponse.json(baseInteractions)
      })
    )

    const { result } = renderHook(
      () =>
        useNewsInteraction(NEWS_ID, {
          initialData: { likes_count: 9, is_liked: true, comments_count: 2 },
          loadComments: false,
        }),
      { wrapper }
    )

    expect(result.current.interactions).toMatchObject({
      likes_count: 9,
      is_liked: true,
      comments_count: 2,
    })
    await act(async () => {
      await new Promise((resolve) => setTimeout(resolve, 0))
    })
    expect(commentRequests).toBe(0)
  })

  it("loads comments page by page with offset and stops after the last page", async () => {
    const { wrapper } = makeWrapper()
    const total = NEWS_COMMENTS_PAGE_SIZE + 3
    const comments: NewsComment[] = Array.from({ length: total }, (_, index) => ({
      id: commentFixtureId(index),
      content: `Comment ${index}`,
      user_id: EXISTING_COMMENT_AUTHOR_ID,
      user_name: "Ann",
      created_at: `2026-06-13T00:00:${String(index).padStart(2, "0")}Z`,
    }))
    const requested: string[] = []
    server.use(
      http.get("*/news/:newsId/interactions", ({ request }) => {
        const params = new URL(request.url).searchParams
        const limit = Number(params.get("limit"))
        const offset = Number(params.get("offset"))
        requested.push(`${limit}:${offset}`)
        return HttpResponse.json({
          likes_count: 0,
          is_liked: false,
          comments: comments.slice(offset, offset + limit),
          comments_count: total,
        })
      })
    )

    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })

    await waitFor(() =>
      expect(result.current.interactions?.comments).toHaveLength(NEWS_COMMENTS_PAGE_SIZE)
    )
    expect(result.current.hasMoreComments).toBe(true)

    await act(async () => {
      result.current.loadMoreComments()
    })
    await waitFor(() => expect(result.current.interactions?.comments).toEqual(comments))
    expect(result.current.hasMoreComments).toBe(false)
    expect(requested).toEqual([
      `${NEWS_COMMENTS_PAGE_SIZE}:0`,
      `${NEWS_COMMENTS_PAGE_SIZE}:${NEWS_COMMENTS_PAGE_SIZE}`,
    ])
  })

  it("appends a new comment to the last loaded page after later pages load", async () => {
    const { wrapper } = makeWrapper()
    const comments: NewsComment[] = Array.from({ length: NEWS_COMMENTS_PAGE_SIZE + 1 }, (_, i) => ({
      id: commentFixtureId(i),
      content: `Comment ${i}`,
      user_id: EXISTING_COMMENT_AUTHOR_ID,
      user_name: "Ann",
      created_at: `2026-06-13T00:00:${String(i).padStart(2, "0")}Z`,
    }))
    server.use(
      http.get("*/news/:newsId/interactions", ({ request }) => {
        const params = new URL(request.url).searchParams
        const limit = Number(params.get("limit"))
        const offset = Number(params.get("offset"))
        return HttpResponse.json({
          likes_count: 0,
          is_liked: false,
          comments: comments.slice(offset, offset + limit),
          comments_count: comments.length,
        })
      }),
      http.post("*/news/:newsId/comment", async ({ request }) => {
        const body = (await request.json()) as { content: string }
        const created: NewsComment = {
          id: commentFixtureId(100),
          content: body.content,
          user_id: SIGNED_IN_USER_ID,
          user_name: "Test User",
          created_at: "2026-06-13T01:00:00Z",
        }
        comments.push(created)
        return HttpResponse.json(created)
      })
    )

    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() =>
      expect(result.current.interactions?.comments).toHaveLength(NEWS_COMMENTS_PAGE_SIZE)
    )
    await act(async () => {
      result.current.loadMoreComments()
    })
    await waitFor(() =>
      expect(result.current.interactions?.comments).toHaveLength(NEWS_COMMENTS_PAGE_SIZE + 1)
    )

    await act(async () => {
      await result.current.addComment("Newest")
    })
    await waitFor(() =>
      expect(result.current.interactions?.comments.at(-1)?.content).toBe("Newest")
    )
    expect(result.current.interactions?.comments).toHaveLength(NEWS_COMMENTS_PAGE_SIZE + 2)
    expect(result.current.hasMoreComments).toBe(false)
  })

  it("reads a cache without pages as an empty summary", async () => {
    const { qc, wrapper } = makeWrapper()
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID, { loadComments: false }), {
      wrapper,
    })

    act(() => {
      qc.setQueryData<InfiniteData<NewsInteractions, number>>(["news", NEWS_ID, "interactions"], {
        pages: [],
        pageParams: [],
      })
    })

    await waitFor(() =>
      expect(result.current.interactions).toEqual({
        likes_count: 0,
        is_liked: false,
        comments: [],
      })
    )
  })

  it("defaults omitted like fields in partial initialData", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID, { initialData: {} }), {
      wrapper,
    })

    expect(result.current.interactions).toMatchObject({
      likes_count: 0,
      is_liked: false,
      comments: [],
      comments_count: 0,
    })
    await waitFor(() => expect(qc.isFetching()).toBe(0))
  })
})

describe("useNewsInteraction — toggleLike", () => {
  it.each([
    { isLiked: false, optimisticCount: 4 },
    { isLiked: true, optimisticCount: 2 },
  ])(
    "updates the like while the request is pending (already liked: $isLiked)",
    async ({ isLiked, optimisticCount }) => {
      const initial = { ...baseInteractions, is_liked: isLiked }
      const authoritative = { ...initial, is_liked: !isLiked, likes_count: 9 }
      const { mutation, refetch, request } = holdInteractionResponses("like", initial)
      const { qc, wrapper } = makeWrapper()
      const { result, unmount } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })

      try {
        await waitFor(() => expect(result.current.interactions).toEqual(initial))
        act(() => result.current.toggleLike())

        await waitForMutationAttempt(qc, request)
        expect(result.current.isLiking).toBe(true)
        expect(result.current.interactions).toEqual({
          ...initial,
          is_liked: !isLiked,
          likes_count: optimisticCount,
        })

        mutation.resolve(new HttpResponse(null, { status: 200 }))
        await waitFor(() => expect(result.current.isLiking).toBe(false))
        expect(qc.isFetching()).toBe(1)
        expect(result.current.interactions?.likes_count).toBe(optimisticCount)

        refetch.resolve(authoritative)
        await waitFor(() => expect(result.current.interactions).toEqual(authoritative))
      } finally {
        unmount()
        qc.clear()
        mutation.resolve(new HttpResponse(null, { status: 200 }))
        refetch.resolve(initial)
      }
    }
  )

  it.each([false, true])(
    "restores a rejected like before refetch resolves (already liked: %s)",
    async (isLiked) => {
      const initial = { ...baseInteractions, is_liked: isLiked }
      const authoritative = { ...initial, likes_count: 7 }
      const { mutation, refetch, request } = holdInteractionResponses("like", initial)
      const { qc, wrapper } = makeWrapper()
      const { result, unmount } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })

      try {
        await waitFor(() => expect(result.current.interactions).toEqual(initial))
        act(() => result.current.toggleLike())
        await waitForMutationAttempt(qc, request)
        expect(result.current.isLiking).toBe(true)
        expect(result.current.interactions).toEqual({
          ...initial,
          is_liked: !isLiked,
          likes_count: isLiked ? 2 : 4,
        })

        mutation.resolve(new HttpResponse(null, { status: 500 }))
        await waitFor(() => expect(result.current.isLiking).toBe(false))
        expect(qc.isFetching()).toBe(1)
        expect(result.current.interactions).toEqual(initial)

        refetch.resolve(authoritative)
        await waitFor(() => expect(result.current.interactions).toEqual(authoritative))
      } finally {
        unmount()
        qc.clear()
        mutation.resolve(new HttpResponse(null, { status: 200 }))
        refetch.resolve(initial)
      }
    }
  )

  it("401 rethrows and does NOT queue", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "401" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))
    expect(await readQueue()).toEqual([])
  })

  it.each([
    ["message", { message: "Network Error" }],
    ["code", { code: "ERR_NETWORK" }],
  ])("queues an online network failure identified by the %s field", async (_field, error) => {
    const postSpy = vi.spyOn(api, "post").mockRejectedValueOnce(error)
    try {
      const { wrapper } = makeWrapper()
      setupServer({ initial: baseInteractions, like: "ok" })
      const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      // Keep the browser online so the queue decision is driven by the
      // structured transport error rather than navigator.onLine.
      setOnline(true)
      act(() => result.current.toggleLike())
      await waitFor(() => expect(result.current.isLiking).toBe(false))

      expect(await readQueue()).toHaveLength(1)
      expect(postSpy).toHaveBeenCalledWith(`/news/${NEWS_ID}/like`)
    } finally {
      postSpy.mockRestore()
    }
  })

  it("rethrows an online non-network error without queuing it", async () => {
    const postSpy = vi.spyOn(api, "post").mockRejectedValueOnce(new Error("server exploded"))
    try {
      const { qc, wrapper } = makeWrapper()
      setupServer({ initial: baseInteractions, like: "ok" })
      const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
      await waitFor(() => expect(result.current.isLoading).toBe(false))

      act(() => result.current.toggleLike())
      await waitFor(() => expect(result.current.isLiking).toBe(false))

      expect(await readQueue()).toEqual([])
      expect(cachedInteractions(qc)).toEqual(baseInteractions)
    } finally {
      postSpy.mockRestore()
    }
  })

  it("offline queues to IndexedDB (mutation treated as success)", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({
      initial: { ...baseInteractions, is_liked: false, likes_count: 3 },
      like: "offline",
    })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)
    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))
    const q = await readQueue()
    expect(q).toHaveLength(1)
    expect(q[0]!.url).toBe(`/api/v1/news/${NEWS_ID}/like`)
    expect(q[0]!.method).toBe("POST")
    expect(q[0]!.payload).toEqual({})
    // offline refetch also errors → optimistic flip is NOT reverted
    const d = cachedInteractions(qc)
    expect(d?.is_liked).toBe(true)
  })

  it("upgrades an existing queue database without recreating its stores", async () => {
    await precreateQueueDatabase()
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)

    act(() => result.current.toggleLike())

    await waitFor(() => expect(result.current.isLiking).toBe(false))
    expect(await readQueue()).toHaveLength(1)
  })

  it("queues offline interactions in a database the service worker already upgraded", async () => {
    const workerDatabase = await openServiceWorkerSchema()
    workerDatabase.close()
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)

    act(() => result.current.toggleLike())

    await waitFor(() => expect(result.current.isLiking).toBe(false))
    expect(await readQueue()).toHaveLength(1)
  })

  it("upgrades a version-3 database without recreating the worker's mutation store", async () => {
    const legacy = await openDatabaseAt(3, createWorkerStores)
    await new Promise<void>((resolve, reject) => {
      const tx = legacy.transaction("pending-mutations", "readwrite")
      tx.objectStore("pending-mutations").add({
        mutationId: "m-kept",
        url: "/api/v1/news/news-1/like",
        method: "POST",
        payload: {},
        timestamp: 1,
        idempotencyKey: "key-kept",
        retryCount: 0,
      })
      tx.oncomplete = () => resolve()
      tx.onerror = () => reject(tx.error)
    })
    legacy.close()

    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)
    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))

    const db = await openDatabaseAt(DB_VERSION)
    try {
      const keptMutations = await new Promise<unknown[]>((resolve, reject) => {
        const req = db.transaction("pending-mutations").objectStore("pending-mutations").getAll()
        req.onsuccess = () => resolve(req.result)
        req.onerror = () => reject(req.error)
      })
      expect(keptMutations).toHaveLength(1)
    } finally {
      db.close()
    }
  })

  it("creates the service worker's stores when the page creates the database first", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)
    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))

    const db = await new Promise<IDBDatabase>((resolve, reject) => {
      const req = indexedDB.open(DB_NAME, DB_VERSION)
      req.onsuccess = () => resolve(req.result)
      req.onerror = () => reject(req.error)
    })
    try {
      expect(db.objectStoreNames.contains("pending-mutations")).toBe(true)
      const reports = db.transaction("pending-reports").objectStore("pending-reports")
      expect(reports.indexNames.contains("dedupeKey")).toBe(true)
    } finally {
      db.close()
    }
  })

  it("registers background sync when the service-worker sync APIs exist", async () => {
    const register = vi.fn().mockResolvedValue(undefined)
    const previousServiceWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const previousSyncManager = Object.getOwnPropertyDescriptor(window, "SyncManager")
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ sync: { register } }) },
    })
    Object.defineProperty(window, "SyncManager", {
      configurable: true,
      value: class SyncManager {},
    })
    expect("serviceWorker" in navigator).toBe(true)
    expect("SyncManager" in window).toBe(true)

    try {
      const { wrapper } = makeWrapper()
      setupServer({
        initial: baseInteractions,
        like: "offline",
      })
      const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
      await waitFor(() => expect(result.current.isLoading).toBe(false))
      setOnline(false)

      act(() => result.current.toggleLike())
      await waitFor(() => expect(register).toHaveBeenCalledWith("news-interaction:sync"))
      await waitFor(() => expect(result.current.isLiking).toBe(false))
    } finally {
      if (previousServiceWorker) {
        Object.defineProperty(navigator, "serviceWorker", previousServiceWorker)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
      if (previousSyncManager) {
        Object.defineProperty(window, "SyncManager", previousSyncManager)
      } else {
        Reflect.deleteProperty(window, "SyncManager")
      }
    }
  })

  it("rolls back an offline like when its queue transaction aborts after request success", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)

    const requestSucceeded = deferred<void>()
    const transactionAborted = deferred<void>()
    const originalAdd = IDBObjectStore.prototype.add
    const addSpy = vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(function (
      ...args: Parameters<IDBObjectStore["add"]>
    ) {
      const request = originalAdd.apply(this, args)
      if (this.name === STORE) {
        request.addEventListener(
          "success",
          () => {
            const transaction = request.transaction
            requestSucceeded.resolve(undefined)
            transaction?.addEventListener("abort", () => transactionAborted.resolve(undefined), {
              once: true,
            })
            transaction?.abort()
          },
          { once: true }
        )
      }
      return request
    })

    try {
      act(() => result.current.toggleLike())
      await requestSucceeded.promise
      await transactionAborted.promise
      await waitFor(() => {
        expect(qc.getMutationCache().getAll()[0]?.state.status).not.toBe("pending")
      })
      expect(qc.getMutationCache().getAll()[0]?.state.status).toBe("error")

      expect(result.current.isLiking).toBe(false)
      expect(cachedInteractions(qc)).toEqual(baseInteractions)
      expect(await readQueue()).toEqual([])
    } finally {
      addSpy.mockRestore()
    }
  })

  it("rejects an offline queue write error and preserves earlier queued entries", async () => {
    const db = await openServiceWorkerSchema()
    try {
      await new Promise<void>((resolve, reject) => {
        const tx = db.transaction(STORE, "readwrite")
        tx.oncomplete = () => resolve()
        tx.onabort = () => reject(tx.error ?? new Error("Could not seed the queue"))
        tx.objectStore(STORE).add({
          id: 1,
          url: "/already-queued",
          payload: {},
          method: "POST",
          timestamp: 1,
        })
      })
    } finally {
      db.close()
    }

    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)

    const transactionErrored = deferred<void>()
    const originalAdd = IDBObjectStore.prototype.add
    const addSpy = vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(function (
      ...args: Parameters<IDBObjectStore["add"]>
    ) {
      const [value] = args
      const request =
        this.name === STORE && typeof value === "object" && value !== null
          ? originalAdd.call(this, { ...value, id: 1 })
          : originalAdd.apply(this, args)
      if (this.name === STORE) {
        request.addEventListener(
          "error",
          () => {
            request.transaction?.addEventListener(
              "error",
              () => transactionErrored.resolve(undefined),
              { once: true }
            )
          },
          { once: true }
        )
      }
      return request
    })

    try {
      act(() => result.current.toggleLike())
      await transactionErrored.promise
      await waitFor(() => {
        expect(qc.getMutationCache().getAll()[0]?.state.status).toBe("error")
      })

      expect(result.current.isLiking).toBe(false)
      expect(cachedInteractions(qc)).toEqual(baseInteractions)
      expect(await readQueue()).toEqual([
        {
          id: 1,
          url: "/already-queued",
          payload: {},
          method: "POST",
          timestamp: 1,
        },
      ])
    } finally {
      addSpy.mockRestore()
    }
  })
  it("settles queued offline mutation when service-worker readiness never resolves", async () => {
    let rejectPost!: (error: unknown) => void
    const networkRequest = new Promise<never>((_resolve, reject) => {
      rejectPost = reject
    })
    const postSpy = vi.spyOn(api, "post").mockImplementationOnce(() => networkRequest)
    const { promise: neverReady } = deferred<never>()
    const previousServiceWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const previousSyncManager = Object.getOwnPropertyDescriptor(window, "SyncManager")
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: neverReady },
    })
    Object.defineProperty(window, "SyncManager", {
      configurable: true,
      value: class SyncManager {},
    })

    try {
      const { wrapper } = makeWrapper()
      setupServer({ initial: baseInteractions })
      const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
      await waitFor(() => expect(result.current.isLoading).toBe(false))
      setOnline(false)

      act(() => result.current.toggleLike())
      await waitFor(() => expect(postSpy).toHaveBeenCalled())
      expect(result.current.isLiking).toBe(true)
      act(() => rejectPost(new Error("Network Error")))

      await waitFor(() => expect(result.current.isLiking).toBe(false), { timeout: 1000 })
      expect(await readQueue()).toHaveLength(1)
    } finally {
      postSpy.mockRestore()
      if (previousServiceWorker) {
        Object.defineProperty(navigator, "serviceWorker", previousServiceWorker)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
      if (previousSyncManager) {
        Object.defineProperty(window, "SyncManager", previousSyncManager)
      } else {
        Reflect.deleteProperty(window, "SyncManager")
      }
    }
  })

  it("keeps the offline mutation when background-sync registration fails", async () => {
    const registrationError = new Error("sync denied")
    const register = vi.fn().mockRejectedValue(registrationError)
    const previousServiceWorker = Object.getOwnPropertyDescriptor(navigator, "serviceWorker")
    const previousSyncManager = Object.getOwnPropertyDescriptor(window, "SyncManager")
    Object.defineProperty(navigator, "serviceWorker", {
      configurable: true,
      value: { ready: Promise.resolve({ sync: { register } }) },
    })
    Object.defineProperty(window, "SyncManager", {
      configurable: true,
      value: class SyncManager {},
    })

    try {
      const { wrapper } = makeWrapper()
      setupServer({ initial: baseInteractions, like: "offline" })
      const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
      await waitFor(() => expect(result.current.isLoading).toBe(false))
      setOnline(false)

      await withExpectedConsole("warn", "Failed to register background sync", async () => {
        act(() => result.current.toggleLike())
        await waitFor(() => expect(register).toHaveBeenCalledWith("news-interaction:sync"))
        await waitFor(() => expect(result.current.isLiking).toBe(false))
      })
      expect(await readQueue()).toHaveLength(1)
    } finally {
      if (previousServiceWorker) {
        Object.defineProperty(navigator, "serviceWorker", previousServiceWorker)
      } else {
        Reflect.deleteProperty(navigator, "serviceWorker")
      }
      if (previousSyncManager) {
        Object.defineProperty(window, "SyncManager", previousSyncManager)
      } else {
        Reflect.deleteProperty(window, "SyncManager")
      }
    }
  })
})

describe("useNewsInteraction — addComment", () => {
  const withComment = (over: Partial<NewsInteractions> = {}): NewsInteractions => ({
    likes_count: 0,
    is_liked: false,
    comments: [
      {
        id: commentFixtureId(0),
        content: "old",
        user_id: EXISTING_COMMENT_AUTHOR_ID,
        user_name: "X",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    comments_count: 1,
    ...over,
  })

  it.each([
    { name: "signed-in author and server count", hasUser: true, count: 20, nextCount: 21 },
    { name: "anonymous author", hasUser: false, count: 1, nextCount: 2 },
    { name: "omitted server count", hasUser: true, count: undefined, nextCount: 2 },
  ])("shows a pending comment with $name", async ({ hasUser, count, nextCount }) => {
    if (!hasUser) setAuthFixture(null)
    const initial = withComment({ comments_count: count })
    const { mutation, refetch, request } = holdInteractionResponses("comment", initial)
    const { qc, wrapper } = makeWrapper()
    const { result, unmount } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    const confirmed: NewsComment = {
      id: commentFixtureId(42),
      content: "hello",
      user_id: hasUser ? SIGNED_IN_USER_ID : PUBLIC_COMMENT_AUTHOR_ID,
      user_name: hasUser ? "Test User" : "You",
      created_at: "2026-06-13T00:00:00Z",
    }
    const authoritative = {
      ...initial,
      comments: [...initial.comments, confirmed],
      comments_count: nextCount,
    }

    try {
      await waitFor(() => expect(result.current.interactions).toEqual(initial))
      const startedAt = Date.now()
      const { settlement: commentResult } = await startMutation(() =>
        result.current.addComment("hello")
      )
      await waitForMutationAttempt(qc, request)
      expect(result.current.isCommenting).toBe(true)
      expect(result.current.interactions?.comments).toHaveLength(2)
      expect(result.current.interactions?.comments_count).toBe(nextCount)
      const pending = result.current.interactions!.comments[1]!
      expect(result.current.interactions?.comments[0]).toEqual(initial.comments[0])
      expect(pending).toMatchObject({
        content: "hello",
        user_name: confirmed.user_name,
      })
      expect(pending.user_id).toBe(hasUser ? SIGNED_IN_USER_ID : "")
      expect(pending.id).not.toBe("")
      expect(pending.id).not.toBe(initial.comments[0]!.id)
      expect(Date.parse(pending.created_at)).toBeGreaterThanOrEqual(startedAt)
      expect(Date.parse(pending.created_at)).toBeLessThanOrEqual(Date.now())

      await act(async () => {
        mutation.resolve(HttpResponse.json(confirmed))
        await commentResult
      })
      expect(await commentResult).toEqual({ status: "fulfilled", value: confirmed })
      await waitFor(() => expect(result.current.isCommenting).toBe(false))
      expect(qc.isFetching()).toBe(1)
      expect(result.current.interactions?.comments).toEqual([...initial.comments, pending])

      refetch.resolve(authoritative)
      await waitFor(() => expect(result.current.interactions).toEqual(authoritative))
    } finally {
      unmount()
      qc.clear()
      mutation.resolve(HttpResponse.json(confirmed))
      refetch.resolve(initial)
    }
  })

  it("restores a rejected comment before refetch resolves", async () => {
    const initial = withComment({ comments_count: 20 })
    const authoritative = { ...initial, likes_count: 7 }
    const { mutation, refetch, request } = holdInteractionResponses("comment", initial)
    const { qc, wrapper } = makeWrapper()
    const { result, unmount } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })

    try {
      await waitFor(() => expect(result.current.interactions).toEqual(initial))
      const { settlement: commentResult } = await startMutation(() =>
        result.current.addComment("nope")
      )
      await waitForMutationAttempt(qc, request)
      expect(result.current.isCommenting).toBe(true)
      expect(result.current.interactions?.comments).toHaveLength(2)
      expect(result.current.interactions?.comments[1]?.content).toBe("nope")
      expect(result.current.interactions?.comments_count).toBe(21)

      await act(async () => {
        mutation.resolve(new HttpResponse(null, { status: 500 }))
        await commentResult
      })
      expect(await commentResult).toMatchObject({
        status: "rejected",
        reason: { response: { status: 500 } },
      })
      await waitFor(() => expect(result.current.isCommenting).toBe(false))
      expect(qc.isFetching()).toBe(1)
      expect(result.current.interactions).toEqual(initial)

      refetch.resolve(authoritative)
      await waitFor(() => expect(result.current.interactions).toEqual(authoritative))
    } finally {
      unmount()
      qc.clear()
      mutation.resolve(new HttpResponse(null, { status: 200 }))
      refetch.resolve(initial)
    }
  })

  it("keeps another news item's fetch running while posting a comment", async () => {
    const initial = withComment()
    const { mutation, refetch, request } = holdInteractionResponses("comment", initial)
    const otherResponse = deferred<NewsInteractions>()
    server.use(
      http.get("*/news/news-other/interactions", async () =>
        HttpResponse.json(await otherResponse.promise)
      )
    )
    const { qc, wrapper } = makeWrapper()
    const { result, unmount } = renderHook(
      () => ({ current: useNewsInteraction(NEWS_ID), other: useNewsInteraction("news-other") }),
      { wrapper }
    )

    try {
      await waitFor(() => expect(result.current.current.interactions).toEqual(initial))
      expect(result.current.other.isLoading).toBe(true)
      const { settlement: commentResult } = await startMutation(() =>
        result.current.current.addComment("hello")
      )

      await waitForMutationAttempt(qc, request)
      expect(result.current.current.isCommenting).toBe(true)
      expect(result.current.other.isLoading).toBe(true)

      otherResponse.resolve(baseInteractions)
      await waitFor(() => expect(result.current.other.isLoading).toBe(false))
      expect(result.current.other.interactions).toEqual(baseInteractions)

      await act(async () => {
        mutation.resolve(new HttpResponse(null, { status: 500 }))
        await commentResult
      })
      expect(await commentResult).toMatchObject({
        status: "rejected",
        reason: { response: { status: 500 } },
      })
      await waitFor(() => expect(result.current.current.isCommenting).toBe(false))
      expect(result.current.current.interactions).toEqual(initial)
      expect(result.current.other.interactions).toEqual(baseInteractions)

      refetch.resolve(initial)
      await waitFor(() => expect(qc.isFetching()).toBe(0))
    } finally {
      unmount()
      qc.clear()
      mutation.resolve(new HttpResponse(null, { status: 200 }))
      refetch.resolve(initial)
      otherResponse.resolve(baseInteractions)
    }
  })

  it("posts a comment before interactions have loaded and then fetches the saved comment", async () => {
    const queryGate = deferred<void>()
    const state = { ...baseInteractions }
    const saved: NewsComment = {
      id: commentFixtureId(43),
      content: "before load",
      user_id: SIGNED_IN_USER_ID,
      user_name: "Test User",
      created_at: "2026-06-13T00:00:00Z",
    }
    const request = { started: false }
    server.use(
      http.get(`*/news/${NEWS_ID}/interactions`, async () => {
        await queryGate.promise
        return HttpResponse.json(state)
      }),
      http.post(`*/news/${NEWS_ID}/comment`, async ({ request: incoming }) => {
        const body = (await incoming.json()) as { content: string }
        state.comments = [{ ...saved, content: body.content }]
        state.comments_count = 1
        request.started = true
        return HttpResponse.json(saved)
      })
    )
    const { qc, wrapper } = makeWrapper()
    const { result, unmount } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })

    try {
      expect(result.current.isLoading).toBe(true)
      expect(result.current.interactions).toBeUndefined()
      const { settlement: commentResult } = await startMutation(() =>
        result.current.addComment("before load")
      )
      await waitForMutationAttempt(qc, request)
      await waitFor(() => expect(result.current.isCommenting).toBe(false))
      expect(await commentResult).toEqual({ status: "fulfilled", value: saved })

      queryGate.resolve()
      await waitFor(() => expect(result.current.isLoading).toBe(false))
      expect(result.current.interactions).toEqual({
        ...baseInteractions,
        comments: [saved],
        comments_count: 1,
      })
    } finally {
      unmount()
      qc.clear()
      queryGate.resolve()
    }
  })

  it("offline queues the comment payload", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: withComment(), comment: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    setOnline(false)
    const { settlement: commentResult } = await startMutation(() =>
      result.current.addComment("offline comment")
    )
    await waitFor(() => expect(result.current.isCommenting).toBe(false))
    expect(await commentResult).toEqual({
      status: "fulfilled",
      value: { isOfflineStore: true },
    })
    const q = await readQueue()
    expect(q).toHaveLength(1)
    expect(q[0]!.url).toBe(`/api/v1/news/${NEWS_ID}/comment`)
    expect(q[0]!.method).toBe("POST")
    expect(q[0]!.payload).toEqual({ content: "offline comment" })
  })
})

describe("useNewsInteraction — updateComment + deleteComment", () => {
  const oneComment = (): NewsInteractions => ({
    likes_count: 0,
    is_liked: false,
    comments: [
      {
        id: commentFixtureId(1),
        content: "orig",
        user_id: EXISTING_COMMENT_AUTHOR_ID,
        user_name: "X",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    comments_count: 1,
  })

  const twoComments = (): NewsInteractions => ({
    likes_count: 0,
    is_liked: false,
    comments: [
      {
        id: commentFixtureId(1),
        content: "a",
        user_id: EXISTING_COMMENT_AUTHOR_ID,
        user_name: "X",
        created_at: "2026-01-01T00:00:00Z",
      },
      {
        id: commentFixtureId(2),
        content: "b",
        user_id: EXISTING_COMMENT_AUTHOR_ID,
        user_name: "X",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    comments_count: 2,
  })

  it("updateComment online edits optimistically", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: oneComment(), patch: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.updateComment(commentFixtureId(1), "edited"))
    await waitFor(() => {
      const d = cachedInteractions(qc)
      expect(d?.comments.find((c) => c.id === commentFixtureId(1))?.content).toBe("edited")
    })
  })

  it("updateComment preserves unrelated comments", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: twoComments(), patch: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(2))
    act(() => result.current.updateComment(commentFixtureId(1), "edited"))
    await waitFor(() => {
      const data = cachedInteractions(qc)
      expect(data?.comments.find((comment) => comment.id === commentFixtureId(2))?.content).toBe(
        "b"
      )
    })
  })

  it("updateComment 500 rolls back", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: oneComment(), patch: "500" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.updateComment(commentFixtureId(1), "x"))
    await waitFor(() => expect(result.current.isUpdatingComment).toBe(false))
    await waitFor(() => {
      const d = cachedInteractions(qc)
      expect(d?.comments.find((c) => c.id === commentFixtureId(1))?.content).toBe("orig")
    })
  })

  it("updateComment offline queues a PATCH", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: oneComment(), patch: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    setOnline(false)
    act(() => result.current.updateComment(commentFixtureId(1), "x"))
    await waitFor(() => expect(result.current.isUpdatingComment).toBe(false))
    const q = await readQueue()
    expect(q[0]!.url).toBe("/api/v1/news/comments/" + commentFixtureId(1))
    expect(q[0]!.method).toBe("PATCH")
    expect(q[0]!.payload).toEqual({ content: "x" })
  })

  it("deleteComment online removes optimistically", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: twoComments(), del: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(2))
    act(() => result.current.deleteComment(commentFixtureId(1)))
    await waitFor(() => {
      const d = cachedInteractions(qc)
      expect(d?.comments.length).toBe(1)
      expect(d?.comments_count).toBe(1)
    })
  })

  it("deleteComment derives the count when the server omits it", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: { ...twoComments(), comments_count: undefined }, del: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(2))
    act(() => result.current.deleteComment(commentFixtureId(1)))
    await waitFor(() => {
      const data = cachedInteractions(qc)
      expect(data?.comments_count).toBe(1)
    })
  })

  it("deleteComment 500 rolls back", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: twoComments(), del: "500" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(2))
    act(() => result.current.deleteComment(commentFixtureId(1)))
    await waitFor(() => expect(result.current.isDeletingComment).toBe(false))
    await waitFor(() => {
      const d = cachedInteractions(qc)
      expect(d?.comments.length).toBe(2)
    })
  })

  it("deleteComment offline queues a DELETE", async () => {
    const { wrapper } = makeWrapper()
    setupServer({
      initial: {
        likes_count: 0,
        is_liked: false,
        comments: [
          {
            id: commentFixtureId(2),
            content: "b",
            user_id: EXISTING_COMMENT_AUTHOR_ID,
            user_name: "X",
            created_at: "2026-01-01T00:00:00Z",
          },
        ],
        comments_count: 1,
      },
      del: "offline",
    })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    setOnline(false)
    act(() => result.current.deleteComment(commentFixtureId(2)))
    await waitFor(() => expect(result.current.isDeletingComment).toBe(false))
    const q = await readQueue()
    expect(q[0]!.url).toBe("/api/v1/news/comments/" + commentFixtureId(2))
    expect(q[0]!.method).toBe("DELETE")
    expect(q[0]!.payload).toEqual({})
  })
})

describe("useNewsInteraction — IndexedDB failure callbacks", () => {
  it("surfaces an IndexedDB open failure from the offline queue attempt", async () => {
    vi.stubGlobal("indexedDB", {
      open: vi.fn(() => {
        const request = {} as IDBOpenDBRequest
        queueMicrotask(() => request.onerror?.(new Event("error")))
        return request
      }),
    })

    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)

    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))
  })

  it("surfaces an IndexedDB add failure after the queue database opens", async () => {
    const onRequestError = vi.fn()
    const addSpy = vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(() => {
      const request = {} as IDBRequest
      queueMicrotask(() => {
        onRequestError()
        request.onerror?.(new Event("error"))
      })
      return request
    })

    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)

    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))
    await waitFor(() => expect(onRequestError).toHaveBeenCalledOnce())
    addSpy.mockRestore()
  })
})

describe("useNewsInteraction — mutations before the query cache resolves", () => {
  it("keeps all optimistic and rollback handlers safe without previous data", async () => {
    let release!: () => void
    const queryGate = new Promise<void>((resolve) => {
      release = resolve
    })
    setupServer({
      initial: baseInteractions,
      like: "500",
      comment: "500",
      patch: "500",
      del: "500",
    })
    server.use(
      http.get("*/news/:newsId/interactions", async () => {
        await queryGate
        return HttpResponse.json(baseInteractions)
      })
    )
    const { qc, wrapper } = makeWrapper()
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })

    let commentResult!: Promise<MutationSettlement<unknown>>
    await act(async () => {
      result.current.toggleLike()
      commentResult = observeMutation(result.current.addComment("before-cache"))
      result.current.updateComment("missing", "before-cache")
      result.current.deleteComment("missing")
      await Promise.resolve()
    })

    await waitFor(() => {
      expect(result.current.isLiking).toBe(false)
      expect(result.current.isCommenting).toBe(false)
      expect(result.current.isUpdatingComment).toBe(false)
      expect(result.current.isDeletingComment).toBe(false)
    })
    expect(await commentResult).toMatchObject({
      status: "rejected",
      reason: { response: { status: 500 } },
    })
    expect(qc.getQueryData(["news", NEWS_ID, "interactions"])).toBeUndefined()

    release()
    await waitFor(() => expect(result.current.isLoading).toBe(false))
  })
})
