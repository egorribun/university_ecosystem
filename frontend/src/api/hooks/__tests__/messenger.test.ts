/**
 * Wave 180 SW3 — messenger factory exports.
 *
 * Verifies the queryOptions factory shape (`chatsQueryKey`,
 * `chatsQueryOptions`, `chatQueryOptions`, `messagesQueryOptions`) for
 * /messenger Phase 5 SSR enable (closes W134 §Honesty #10).
 *
 * Tests parallel W134 SW2 sessions.test.ts pattern. The 3 factories
 * extracted in W180 SW3 mirror the W129 (events.ts, news.ts), W130
 * (schedule.ts), W133 (users.ts), W134 SW2 (sessions.ts) convention:
 * pure functions returning `{ queryKey, queryFn, staleTime, gcTime,
 * networkMode, retry, retryDelay }` shapes that consumers spread + add
 * `enabled` gates over.
 *
 * Cache identity verification: queryKey tuples match pre-W180 inline
 * shapes from useMessengerController.ts (line 69 + 75 + 82) so the
 * factory refactor preserves React Query cache continuity.
 */
import { AxiosError, type AxiosResponse } from "axios"
import { afterEach, describe, expect, it, vi } from "vitest"

import { chatApi } from "@/api/chat"
import {
  chatQueryKey,
  chatQueryOptions,
  deniesChatAccess,
  chatsQueryKey,
  chatsQueryOptions,
  messagesQueryKey,
  messagesQueryOptions,
  reactorsQueryKey,
  reactorsQueryOptions,
} from "@/api/hooks/messenger"

afterEach(() => {
  vi.restoreAllMocks()
})

describe("chatsQueryKey", () => {
  it("returns the canonical ['chats'] tuple matching pre-W180 inline key", () => {
    expect(chatsQueryKey).toEqual(["chats"])
  })

  it("matches chatsQueryOptions().queryKey reference identity", () => {
    expect(chatsQueryOptions().queryKey).toBe(chatsQueryKey)
  })
})

describe("chatsQueryOptions", () => {
  it("preserves W180 SW3 baseline (W134 SW2 mirror): staleTime 30s, gcTime 5min, online, retry 2", () => {
    const opts = chatsQueryOptions()
    expect(opts.staleTime).toBe(30_000)
    expect(opts.gcTime).toBe(5 * 60_000)
    expect(opts.networkMode).toBe("online")
    expect(opts.retry).toBe(2)
    expect(typeof opts.retryDelay).toBe("function")
  })

  it("retryDelay exponential backoff caps at 10 seconds (FIX-68-05 mirror)", () => {
    const opts = chatsQueryOptions()
    const delay = opts.retryDelay as (n: number) => number
    expect(delay(0)).toBe(1_000)
    expect(delay(1)).toBe(2_000)
    expect(delay(2)).toBe(4_000)
    expect(delay(3)).toBe(8_000)
    expect(delay(4)).toBe(10_000) // capped
    expect(delay(10)).toBe(10_000) // still capped
  })

  it("queryFn is callable (function shape; not invoked here — would hit network)", () => {
    const opts = chatsQueryOptions()
    expect(typeof opts.queryFn).toBe("function")
  })

  it("queryFn without a consuming client fetches only the first page through chatApi", async () => {
    const page = { items: [], has_more: false, next_cursor: null }
    const getChats = vi.spyOn(chatApi, "getChats").mockResolvedValue(page)
    const signal = new AbortController().signal
    const opts = chatsQueryOptions()

    await expect(
      (opts.queryFn as (ctx: { signal: AbortSignal }) => Promise<unknown>)({ signal })
    ).resolves.toBe(page)

    expect(getChats).toHaveBeenCalledExactlyOnceWith(undefined, 20, signal)
  })
})

describe("chatQueryKey", () => {
  it("returns ['chats', chatId] tuple matching pre-W180 inline key", () => {
    expect(chatQueryKey("chat-abc")).toEqual(["chats", "chat-abc"])
  })

  it("produces distinct keys for different chatId values (cache slot isolation)", () => {
    expect(chatQueryKey("chat-a")).not.toEqual(chatQueryKey("chat-b"))
  })

  it("matches chatQueryOptions(chatId).queryKey for the same chatId", () => {
    expect(chatQueryOptions("chat-xyz").queryKey).toEqual(chatQueryKey("chat-xyz"))
  })
})

describe("chatQueryOptions", () => {
  it("queryKey contains empty-string fallback when chatId is undefined (defensive)", () => {
    // Consumer must add `enabled: !!chatId` gate to prevent fetch; the
    // empty-string queryKey is a defensive cache-slot placeholder that
    // never gets populated under proper `enabled` gating.
    expect(chatQueryOptions(undefined).queryKey).toEqual(["chats", ""])
  })

  it("preserves W180 SW3 baseline shape (same as chatsQueryOptions)", () => {
    const opts = chatQueryOptions("chat-x")
    expect(opts.staleTime).toBe(30_000)
    expect(opts.gcTime).toBe(5 * 60_000)
    expect(opts.networkMode).toBe("online")
    expect(opts.retry).toBe(2)
  })

  it("queryFn throws when chatId is undefined (defensive guard for missing enabled gate)", async () => {
    const opts = chatQueryOptions(undefined)
    await expect(
      // queryFn signature uses signal arg from QueryFunctionContext
      (opts.queryFn as (ctx: { signal: AbortSignal }) => Promise<unknown>)({
        signal: new AbortController().signal,
      })
    ).rejects.toThrow("chatId required")
  })

  const httpError = (status: number) =>
    new AxiosError("request failed", "ERR_BAD_REQUEST", undefined, undefined, {
      status,
    } as AxiosResponse)
  const run = (chatId: string) =>
    (chatQueryOptions(chatId).queryFn as (ctx: { signal: AbortSignal }) => Promise<unknown>)({
      signal: new AbortController().signal,
    })

  it.each([403, 404])(
    "queryFn resolves null when the server denies the chat (%i)",
    async (status) => {
      vi.spyOn(chatApi, "getChat").mockRejectedValue(httpError(status))
      await expect(run("chat-x")).resolves.toBeNull()
    }
  )

  it("queryFn rethrows other failures so the cached chat survives them", async () => {
    const failure = httpError(503)
    vi.spyOn(chatApi, "getChat").mockRejectedValue(failure)
    await expect(run("chat-x")).rejects.toBe(failure)
  })

  it("queryFn returns the chat the server sends", async () => {
    const chat = { id: "chat-x" } as Awaited<ReturnType<typeof chatApi.getChat>>
    vi.spyOn(chatApi, "getChat").mockResolvedValue(chat)
    await expect(run("chat-x")).resolves.toBe(chat)
  })
})

describe("deniesChatAccess", () => {
  it.each([
    [403, true],
    [404, true],
    [401, false],
    [500, false],
  ])("status %i -> %s", (status, denied) => {
    const error = new AxiosError("x", "ERR", undefined, undefined, {
      status,
    } as AxiosResponse)
    expect(deniesChatAccess(error)).toBe(denied)
  })

  it("is false for errors without an HTTP response", () => {
    expect(deniesChatAccess(new Error("offline"))).toBe(false)
    expect(deniesChatAccess(new AxiosError("network"))).toBe(false)
  })
})

describe("messagesQueryKey", () => {
  it("returns ['messages', chatId] tuple matching pre-W180 inline key", () => {
    expect(messagesQueryKey("chat-msg-1")).toEqual(["messages", "chat-msg-1"])
  })

  it("matches messagesQueryOptions(chatId).queryKey for the same chatId", () => {
    expect(messagesQueryOptions("chat-q").queryKey).toEqual(messagesQueryKey("chat-q"))
  })
})

describe("messagesQueryOptions", () => {
  it("queryKey uses empty-string fallback when chatId is null (defensive)", () => {
    expect(messagesQueryOptions(null).queryKey).toEqual(["messages", ""])
  })

  it("preserves W180 SW3 baseline shape", () => {
    const opts = messagesQueryOptions("chat-y")
    expect(opts.staleTime).toBe(30_000)
    expect(opts.gcTime).toBe(5 * 60_000)
    expect(opts.networkMode).toBe("online")
    expect(opts.retry).toBe(2)
  })

  it("queryFn returns empty paginated response when chatId is null (defensive, NOT throwing)", async () => {
    // Pre-W180 useMessengerController line 83-86 fallback shape:
    // `{ items: [], has_more: false, next_cursor: null }`. Preserved in
    // factory for cache stability (React Query would otherwise see
    // undefined and refetch eagerly).
    const opts = messagesQueryOptions(null)
    const result = await (
      opts.queryFn as (ctx: { signal: AbortSignal }) => Promise<{
        items: unknown[]
        has_more: boolean
        next_cursor: string | null
      }>
    )({ signal: new AbortController().signal })
    expect(result).toEqual({ items: [], has_more: false, next_cursor: null })
  })
})

describe("queryKey cross-factory identity", () => {
  it("chatsQueryKey is a const tuple (reference-stable across imports)", () => {
    expect(chatsQueryKey).toBe(chatsQueryOptions().queryKey)
  })

  it("chat + chats keys are distinct (no collision between list + single fetches)", () => {
    expect(chatsQueryKey).not.toEqual(chatQueryKey("any-id"))
    expect(chatQueryKey("any-id")).not.toEqual(messagesQueryKey("any-id"))
  })
})

describe("reactorsQueryKey (W207 SW6)", () => {
  it("returns the ['reactors', chatId, messageId, emoji] 4-tuple", () => {
    expect(reactorsQueryKey("chat-1", "msg-1", "👍")).toEqual(["reactors", "chat-1", "msg-1", "👍"])
  })

  it("matches reactorsQueryOptions(...).queryKey for the same args", () => {
    expect(reactorsQueryOptions("c", "m", "❤️").queryKey).toEqual(reactorsQueryKey("c", "m", "❤️"))
  })

  it("keys distinctly per emoji so each reactor list caches independently", () => {
    expect(reactorsQueryKey("c", "m", "👍")).not.toEqual(reactorsQueryKey("c", "m", "❤️"))
  })
})

describe("reactorsQueryOptions (W207 SW6)", () => {
  it("preserves the W180 SW3 baseline factory shape (on-demand reactor list)", () => {
    const opts = reactorsQueryOptions("c", "m", "😢")
    expect(opts.staleTime).toBe(30_000)
    expect(opts.gcTime).toBe(5 * 60_000)
    expect(opts.networkMode).toBe("online")
    expect(opts.retry).toBe(2)
    expect(typeof opts.queryFn).toBe("function")
  })
})
