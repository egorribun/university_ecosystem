import {
  dehydrate,
  MutationCache,
  onlineManager,
  QueryClient,
  QueryClientProvider,
} from "@tanstack/react-query"
import { act, renderHook, waitFor } from "@testing-library/react"
import { CanceledError } from "axios"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"
import type { PropsWithChildren } from "react"

import api from "@/api/client"
import { persistOptions } from "@/app/queryClient"
import { invalidateSessionEpoch } from "@/stores/sessionEpoch"
import { useAuthStore } from "@/stores/useAuthStore"
import type { UserState } from "@/types/Auth"
import { useNewsInteraction } from "../useNewsInteraction"

vi.mock("@/contexts/AuthContext", () => ({
  useAuth: () => ({ user: { id: "author", full_name: "Author" } }),
}))

const newsId = "00000000-0000-4000-8000-000000000001"
const comment = {
  id: "00000000-0000-4000-8000-000000000002",
  user_id: "author",
  user_name: "Author",
  content: "Original",
  created_at: "2026-10-01T12:00:00Z",
}
const initial = { likes_count: 2, is_liked: false, comments: [comment], comments_count: 1 }
const oldOnline = Object.getOwnPropertyDescriptor(navigator, "onLine")

beforeEach(() => {
  useAuthStore.setState({ user: { id: "author" } as UserState, loading: false })
  Object.defineProperty(navigator, "onLine", { configurable: true, value: false })
})
afterEach(() => {
  onlineManager.setOnline(true)
  useAuthStore.setState({ user: null, loading: true })
  if (oldOnline) Object.defineProperty(navigator, "onLine", oldOnline)
  else Reflect.deleteProperty(navigator, "onLine")
  vi.restoreAllMocks()
})

describe("AUD-375 News offline mutations", () => {
  it.each(["like", "create", "edit", "delete"] as const)(
    "does not persist pending %s interaction data",
    async (operation) => {
      onlineManager.setOnline(true)
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      client.setQueryData(["news", newsId, "interactions"], { pages: [initial], pageParams: [0] })
      client.setQueryData(["news", "list", { language: "en", limit: 12 }], {
        pages: [],
        pageParams: [],
      })
      client.setQueryData(["news", newsId, "en"], { title: "Saved article" })
      let reject!: (error: Error) => void
      const request = new Promise<never>((_resolve, fail) => {
        reject = fail
      })
      const post = vi.spyOn(api, "post").mockReturnValue(request)
      const patch = vi.spyOn(api, "patch").mockReturnValue(request)
      const del = vi.spyOn(api, "delete").mockReturnValue(request)
      const wrapper = ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      const { result, unmount } = renderHook(
        () => useNewsInteraction(newsId, { loadComments: false }),
        { wrapper }
      )
      try {
        act(() => {
          if (operation === "like") void result.current.toggleLikeAsync().catch(() => undefined)
          if (operation === "create")
            void result.current.addComment("private pending draft").catch(() => undefined)
          if (operation === "edit")
            void result.current
              .updateCommentAsync(comment.id, "private pending draft")
              .catch(() => undefined)
          if (operation === "delete")
            void result.current.deleteCommentAsync(comment.id).catch(() => undefined)
        })
        await waitFor(() =>
          expect(
            operation === "edit" ? patch : operation === "delete" ? del : post
          ).toHaveBeenCalledOnce()
        )
        const snapshot = dehydrate(client, persistOptions.dehydrateOptions)
        expect(JSON.stringify(snapshot.queries)).not.toContain("private pending draft")
        expect(snapshot.queries.map((query) => query.queryKey)).toEqual([
          ["news", "list", { language: "en", limit: 12 }],
          ["news", newsId, "en"],
        ])
        expect(snapshot.mutations).toEqual([])
      } finally {
        await act(async () => reject(new Error("Network Error")))
        unmount()
        client.clear()
      }
    }
  )

  it.each(["like", "create", "edit", "delete"] as const)(
    "fails instead of pausing an offline %s",
    async (operation) => {
      onlineManager.setOnline(false)
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      client.setQueryData(["news", newsId, "interactions"], { pages: [initial], pageParams: [0] })
      const post = vi.spyOn(api, "post").mockRejectedValue(new Error("Network Error"))
      const patch = vi.spyOn(api, "patch").mockRejectedValue(new Error("Network Error"))
      const del = vi.spyOn(api, "delete").mockRejectedValue(new Error("Network Error"))
      const wrapper = ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      const { result, unmount } = renderHook(
        () => useNewsInteraction(newsId, { loadComments: false }),
        { wrapper }
      )
      try {
        act(() => {
          if (operation === "like") void result.current.toggleLikeAsync().catch(() => undefined)
          if (operation === "create")
            void result.current.addComment("offline draft").catch(() => undefined)
          if (operation === "edit")
            void result.current
              .updateCommentAsync(comment.id, "offline draft")
              .catch(() => undefined)
          if (operation === "delete")
            void result.current.deleteCommentAsync(comment.id).catch(() => undefined)
        })
        await waitFor(
          () => expect(client.getMutationCache().getAll()[0]?.state.status).toBe("error"),
          { timeout: 3000 }
        )
        expect(
          operation === "edit" ? patch : operation === "delete" ? del : post
        ).toHaveBeenCalledOnce()
      } finally {
        unmount()
        client.clear()
      }
    }
  )
  it.each(["like", "create", "edit", "delete"] as const)(
    "does not restore the previous account cache when an old %s fails after session change",
    async (operation) => {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      const key = ["news", newsId, "interactions"] as const
      client.setQueryData(key, { pages: [initial], pageParams: [0] })
      let reject!: (error: Error) => void
      const request = new Promise<never>((_resolve, fail) => {
        reject = fail
      })
      const post = vi.spyOn(api, "post").mockReturnValue(request)
      const patch = vi.spyOn(api, "patch").mockReturnValue(request)
      const del = vi.spyOn(api, "delete").mockReturnValue(request)
      const wrapper = ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      const { result, unmount } = renderHook(
        () => useNewsInteraction(newsId, { loadComments: false }),
        { wrapper }
      )
      try {
        act(() => {
          if (operation === "like") void result.current.toggleLikeAsync().catch(() => undefined)
          if (operation === "create") void result.current.addComment("draft").catch(() => undefined)
          if (operation === "edit")
            void result.current.updateCommentAsync(comment.id, "draft").catch(() => undefined)
          if (operation === "delete")
            void result.current.deleteCommentAsync(comment.id).catch(() => undefined)
        })
        await waitFor(() =>
          expect(
            operation === "edit" ? patch : operation === "delete" ? del : post
          ).toHaveBeenCalledOnce()
        )
        const successor = { ...initial, likes_count: 42, comments: [] }
        act(() => {
          invalidateSessionEpoch()
          useAuthStore.setState({ user: { id: "other-user" } as UserState, loading: false })
          client.setQueryData(key, { pages: [successor], pageParams: [0] })
        })
        await act(async () => reject(new Error("Network Error")))
        await waitFor(() => expect(client.isMutating()).toBe(0))
        expect(client.getQueryData(key)).toEqual({ pages: [successor], pageParams: [0] })
      } finally {
        unmount()
        client.clear()
      }
    }
  )

  it.each(["like", "create", "edit", "delete"] as const)(
    "does not cancel or send a stale %s when the session changes immediately",
    async (operation) => {
      let release!: () => void
      const preflight = new Promise<void>((resolve) => {
        release = resolve
      })
      const client = new QueryClient({
        mutationCache: new MutationCache({ onMutate: () => preflight }),
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      const key = ["news", newsId, "interactions"] as const
      client.setQueryData(key, { pages: [initial], pageParams: [0] })
      const cancel = vi.spyOn(client, "cancelQueries")
      const post = vi.spyOn(api, "post")
      const patch = vi.spyOn(api, "patch")
      const del = vi.spyOn(api, "delete")
      const wrapper = ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      const { result, unmount } = renderHook(
        () => useNewsInteraction(newsId, { loadComments: false }),
        { wrapper }
      )
      try {
        const successor = { ...initial, likes_count: 42, comments: [] }
        act(() => {
          if (operation === "like") void result.current.toggleLikeAsync().catch(() => undefined)
          if (operation === "create") void result.current.addComment("draft").catch(() => undefined)
          if (operation === "edit")
            void result.current.updateCommentAsync(comment.id, "draft").catch(() => undefined)
          if (operation === "delete")
            void result.current.deleteCommentAsync(comment.id).catch(() => undefined)
          invalidateSessionEpoch()
          useAuthStore.setState({ user: { id: "other-user" } as UserState, loading: false })
          client.setQueryData(key, { pages: [successor], pageParams: [0] })
        })
        await act(async () => release())
        await waitFor(() =>
          expect(client.getMutationCache().getAll()[0]?.state.status).toBe("error")
        )
        expect(cancel).not.toHaveBeenCalled()
        expect(post).not.toHaveBeenCalled()
        expect(patch).not.toHaveBeenCalled()
        expect(del).not.toHaveBeenCalled()
        expect(client.getQueryData(key)).toEqual({ pages: [successor], pageParams: [0] })
      } finally {
        release()
        unmount()
        client.clear()
      }
    }
  )

  it.each(["like", "create", "edit", "delete"] as const)(
    "does not send a stale %s when session changes during query cancellation",
    async (operation) => {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      const key = ["news", newsId, "interactions"] as const
      client.setQueryData(key, { pages: [initial], pageParams: [0] })
      let release!: () => void
      const cancellation = new Promise<void>((resolve) => {
        release = resolve
      })
      const cancel = vi.spyOn(client, "cancelQueries").mockReturnValue(cancellation)
      const post = vi.spyOn(api, "post")
      const patch = vi.spyOn(api, "patch")
      const del = vi.spyOn(api, "delete")
      const wrapper = ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      const { result, unmount } = renderHook(
        () => useNewsInteraction(newsId, { loadComments: false }),
        { wrapper }
      )
      try {
        act(() => {
          if (operation === "like") void result.current.toggleLikeAsync().catch(() => undefined)
          if (operation === "create") void result.current.addComment("draft").catch(() => undefined)
          if (operation === "edit")
            void result.current.updateCommentAsync(comment.id, "draft").catch(() => undefined)
          if (operation === "delete")
            void result.current.deleteCommentAsync(comment.id).catch(() => undefined)
        })
        await waitFor(() => expect(cancel).toHaveBeenCalledOnce())
        const successor = { ...initial, likes_count: 42, comments: [] }
        act(() => {
          invalidateSessionEpoch()
          useAuthStore.setState({ user: { id: "other-user" } as UserState, loading: false })
          client.setQueryData(key, { pages: [successor], pageParams: [0] })
        })
        await act(async () => release())
        await waitFor(() =>
          expect(client.getMutationCache().getAll()[0]?.state.status).toBe("error")
        )
        expect(post).not.toHaveBeenCalled()
        expect(patch).not.toHaveBeenCalled()
        expect(del).not.toHaveBeenCalled()
        expect(client.getQueryData(key)).toEqual({ pages: [successor], pageParams: [0] })
      } finally {
        release()
        unmount()
        client.clear()
      }
    }
  )
  it.each(["like", "create", "edit", "delete", "stale cancellation"] as const)(
    "fails closed and rolls back %s without opening IndexedDB",
    async (operation) => {
      const client = new QueryClient({
        defaultOptions: { queries: { retry: false }, mutations: { retry: false } },
      })
      client.setQueryData(["news", newsId, "interactions"], { pages: [initial], pageParams: [0] })
      const failure =
        operation === "stale cancellation"
          ? new CanceledError("session changed")
          : new Error("Network Error")
      vi.spyOn(api, "post").mockRejectedValue(failure)
      vi.spyOn(api, "patch").mockRejectedValue(failure)
      vi.spyOn(api, "delete").mockRejectedValue(failure)
      const open = vi.spyOn(indexedDB, "open")
      const wrapper = ({ children }: PropsWithChildren) => (
        <QueryClientProvider client={client}>{children}</QueryClientProvider>
      )
      const { result, unmount } = renderHook(
        () => useNewsInteraction(newsId, { loadComments: false }),
        { wrapper }
      )
      try {
        act(() => {
          if (operation === "like") void result.current.toggleLikeAsync().catch(() => undefined)
          if (operation === "stale cancellation") result.current.toggleLike()
          if (operation === "create")
            void result.current.addComment("offline draft").catch(() => undefined)
          if (operation === "edit") result.current.updateComment(comment.id, "offline edit")
          if (operation === "delete") result.current.deleteComment(comment.id)
        })
        await waitFor(
          () => expect(client.getMutationCache().getAll()[0]?.state.status).toBe("error"),
          { timeout: 3000 }
        )
        expect(open).not.toHaveBeenCalled()
        expect(result.current.interactions).toEqual(initial)
      } finally {
        unmount()
        client.clear()
      }
    }
  )
})
