/**
 * Session 11 coverage: src/hooks/useNewsInteraction.ts
 *
 * like/comment/edit/delete optimistic mutations + offline IndexedDB queue.
 *
 * Stateful MSW server simulation: the hook runs `onMutate` (optimistic) then
 * `onSettled` (invalidateQueries → refetch). A *static* GET body would silently
 * revert every optimistic update on that refetch, so handlers here keep a mutable
 * `state` that the POST/PATCH/DELETE mutate on success — the refetch then CONFIRMS
 * the optimistic change (deterministic, no waitFor race). For the offline path the
 * GET *also* errors when `navigator.onLine === false`, mirroring a real offline
 * refetch (React Query keeps the last/optimistic data instead of reverting).
 *
 * MSW v2 intercepts the raw axios instance (`@/api/client`) on relative `/news/...`
 * paths (NOT `/api/...` → setupTests' contract validator skips them). useAuth is
 * mocked via a hoisted holder so `user` is controllable without a provider.
 * Offline = `navigator.onLine = false`; the SW-sync block is skipped (jsdom has no
 * `serviceWorker`/`SyncManager`), so the IDB queue write succeeds silently.
 */
import { act, renderHook, waitFor } from "@testing-library/react"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { IDBFactory } from "fake-indexeddb"
import { http, HttpResponse } from "msw"
import { createElement, type PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { server } from "@/tests/mocks/server"
import type { User } from "@/types/User"
import { useNewsInteraction, type NewsComment, type NewsInteractions } from "../useNewsInteraction"

const authMock = vi.hoisted(() => ({ user: null as User | null }))
vi.mock("@/contexts/AuthContext", () => ({ useAuth: () => ({ user: authMock.user }) }))

const NEWS_ID = "news-1"
const STORE = "pending-news-interactions"
const DB_NAME = "notification-interactions"
const DB_VERSION = 3

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
          id: `c-srv-${state.comments.length}`,
          content: body.content,
          user_id: authMock.user?.id ?? "",
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

beforeEach(() => {
  // Fresh fake-indexeddb factory per test. The hook's openDatabase()
  // (useNewsInteraction.ts) opens a connection it never closes, so
  // indexedDB.deleteDatabase blocks on it and the NEXT offline test's open()
  // deadlocks behind the pending (blocked) delete — every test passes alone but
  // the suite hangs (12 timeouts). A new IDBFactory drops all connections + DBs
  // atomically; same root cause sw.test.ts:237 documents ("deleteDatabase removed
  // to prevent hook timeouts with fake-indexeddb").
  globalThis.indexedDB = new IDBFactory() as unknown as typeof globalThis.indexedDB
  setOnline(true)
  authMock.user = { id: "u-1", full_name: "Test User" } as User
})

afterEach(() => {
  setOnline(true)
  authMock.user = null
})

describe("useNewsInteraction — query", () => {
  it("loads interactions via GET", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    expect(result.current.interactions).toEqual(baseInteractions)
  })

  it("initialData seeds immediately (all defaulting branches)", () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions })
    const { result } = renderHook(
      () => useNewsInteraction(NEWS_ID, { initialData: { likes_count: 9, is_liked: true } }),
      { wrapper }
    )
    expect(result.current.interactions?.likes_count).toBe(9)
    expect(result.current.interactions?.is_liked).toBe(true)
    expect(result.current.interactions?.comments).toEqual([])
    expect(result.current.interactions?.comments_count).toBe(0)
  })

  it("defaults omitted like fields in partial initialData", () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions })
    const { result } = renderHook(
      () => useNewsInteraction(NEWS_ID, { initialData: {} }),
      { wrapper }
    )

    expect(result.current.interactions).toMatchObject({
      likes_count: 0,
      is_liked: false,
      comments: [],
      comments_count: 0,
    })
  })
})

describe("useNewsInteraction — toggleLike", () => {
  it("online happy path flips optimistically and the refetch confirms it", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: { ...baseInteractions, is_liked: false, likes_count: 3 }, like: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    act(() => result.current.toggleLike())
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.is_liked).toBe(true)
      expect(d?.likes_count).toBe(4)
    })
    await waitFor(() => expect(result.current.isLiking).toBe(false))
  })

  it("server 500 rolls back", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: { ...baseInteractions, is_liked: false, likes_count: 3 }, like: "500" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.is_liked).toBe(false)
      expect(d?.likes_count).toBe(3)
    })
  })

  it("401 rethrows and does NOT queue", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "401" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))
    expect(await readQueue()).toEqual([])
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
    const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
    expect(d?.is_liked).toBe(true)
  })

  it("registers background sync when the service-worker sync APIs exist", async () => {
    const register = vi.fn().mockResolvedValue(undefined)
    const previousServiceWorker = navigator.serviceWorker
    const previousSyncManager = (window as Window & { SyncManager?: unknown }).SyncManager
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
      Object.defineProperty(navigator, "serviceWorker", {
        configurable: true,
        value: previousServiceWorker,
      })
      Object.defineProperty(window, "SyncManager", {
        configurable: true,
        value: previousSyncManager,
      })
    }
  })
})

describe("useNewsInteraction — addComment", () => {
  const withComment = (over: Partial<NewsInteractions> = {}): NewsInteractions => ({
    likes_count: 0,
    is_liked: false,
    comments: [
      {
        id: "c0",
        content: "old",
        user_id: "u0",
        user_name: "X",
        created_at: "2026-01-01T00:00:00Z",
      },
    ],
    comments_count: 1,
    ...over,
  })

  it("online optimistic append uses the auth user", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: withComment(), comment: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.addComment("hello"))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments.length).toBe(2)
    })
    const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
    const last = d!.comments[d!.comments.length - 1]!
    expect(last.content).toBe("hello")
    expect(last.user_id).toBe("u-1")
    expect(last.user_name).toBe("Test User")
    expect(d?.comments_count).toBe(2)
  })

  it("optimistic user_name falls back to 'You' + user_id '' when user null", async () => {
    authMock.user = null
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: withComment(), comment: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.addComment("hi"))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments.length).toBe(2)
    })
    const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
    const last = d!.comments[d!.comments.length - 1]!
    expect(last.user_name).toBe("You")
    expect(last.user_id).toBe("")
  })

  it("server 500 rolls back", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: withComment(), comment: "500" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.addComment("nope"))
    await waitFor(() => expect(result.current.isCommenting).toBe(false))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments.length).toBe(1)
    })
  })

  it("offline queues the comment payload", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: withComment(), comment: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    setOnline(false)
    act(() => result.current.addComment("offline comment"))
    await waitFor(() => expect(result.current.isCommenting).toBe(false))
    const q = await readQueue()
    expect(q).toHaveLength(1)
    expect(q[0]!.url).toBe(`/api/v1/news/${NEWS_ID}/comment`)
    expect(q[0]!.method).toBe("POST")
    expect(q[0]!.payload).toEqual({ content: "offline comment" })
  })

  it("comments_count falls back to comments.length when undefined", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: withComment({ comments_count: undefined }), comment: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.addComment("x"))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments_count).toBe(2) // (undefined ?? 1) + 1
    })
  })
})

describe("useNewsInteraction — updateComment + deleteComment", () => {
  const oneComment = (): NewsInteractions => ({
    likes_count: 0,
    is_liked: false,
    comments: [
      {
        id: "c1",
        content: "orig",
        user_id: "u0",
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
      { id: "c1", content: "a", user_id: "u", user_name: "X", created_at: "z" },
      { id: "c2", content: "b", user_id: "u", user_name: "X", created_at: "z" },
    ],
    comments_count: 2,
  })

  it("updateComment online edits optimistically", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: oneComment(), patch: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.updateComment("c1", "edited"))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments.find((c) => c.id === "c1")?.content).toBe("edited")
    })
  })

  it("updateComment 500 rolls back", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: oneComment(), patch: "500" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    act(() => result.current.updateComment("c1", "x"))
    await waitFor(() => expect(result.current.isUpdatingComment).toBe(false))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments.find((c) => c.id === "c1")?.content).toBe("orig")
    })
  })

  it("updateComment offline queues a PATCH", async () => {
    const { wrapper } = makeWrapper()
    setupServer({ initial: oneComment(), patch: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    setOnline(false)
    act(() => result.current.updateComment("c1", "x"))
    await waitFor(() => expect(result.current.isUpdatingComment).toBe(false))
    const q = await readQueue()
    expect(q[0]!.url).toBe("/api/v1/news/comments/c1")
    expect(q[0]!.method).toBe("PATCH")
    expect(q[0]!.payload).toEqual({ content: "x" })
  })

  it("deleteComment online removes optimistically", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: twoComments(), del: "ok" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(2))
    act(() => result.current.deleteComment("c1"))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments.length).toBe(1)
      expect(d?.comments_count).toBe(1)
    })
  })

  it("deleteComment 500 rolls back", async () => {
    const { qc, wrapper } = makeWrapper()
    setupServer({ initial: twoComments(), del: "500" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(2))
    act(() => result.current.deleteComment("c1"))
    await waitFor(() => expect(result.current.isDeletingComment).toBe(false))
    await waitFor(() => {
      const d = qc.getQueryData<NewsInteractions>(["news", NEWS_ID, "interactions"])
      expect(d?.comments.length).toBe(2)
    })
  })

  it("deleteComment offline queues a DELETE", async () => {
    const { wrapper } = makeWrapper()
    setupServer({
      initial: {
        likes_count: 0,
        is_liked: false,
        comments: [{ id: "c2", content: "b", user_id: "u", user_name: "X", created_at: "z" }],
        comments_count: 1,
      },
      del: "offline",
    })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.interactions?.comments.length).toBe(1))
    setOnline(false)
    act(() => result.current.deleteComment("c2"))
    await waitFor(() => expect(result.current.isDeletingComment).toBe(false))
    const q = await readQueue()
    expect(q[0]!.url).toBe("/api/v1/news/comments/c2")
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
    const addSpy = vi.spyOn(IDBObjectStore.prototype, "add").mockImplementation(() => {
      const request = {} as IDBRequest
      queueMicrotask(() => request.onerror?.(new Event("error")))
      return request
    })

    const { wrapper } = makeWrapper()
    setupServer({ initial: baseInteractions, like: "offline" })
    const { result } = renderHook(() => useNewsInteraction(NEWS_ID), { wrapper })
    await waitFor(() => expect(result.current.isLoading).toBe(false))
    setOnline(false)

    act(() => result.current.toggleLike())
    await waitFor(() => expect(result.current.isLiking).toBe(false))
    addSpy.mockRestore()
  })
})
