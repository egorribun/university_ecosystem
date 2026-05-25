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
import { describe, expect, it } from "vitest"

import {
  chatQueryKey,
  chatQueryOptions,
  chatsQueryKey,
  chatsQueryOptions,
  messagesQueryKey,
  messagesQueryOptions,
} from "@/api/hooks/messenger"

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
