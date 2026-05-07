/**
 * Wave 135 SW1 — sessions factory exports.
 *
 * Verifies the factory pattern shape (`sessionsQueryKey`,
 * `sessionsQueryOptions`) AND the new mutation cache helpers
 * (`updateSessionInCache`, `invalidateSessions`) introduced to close
 * W134 §Honesty #5 (mutation paths NOT migrated to factory).
 */
import { QueryClient } from "@tanstack/react-query"
import { describe, expect, it, vi } from "vitest"

import {
  invalidateSessions,
  sessionsQueryKey,
  sessionsQueryOptions,
  updateSessionInCache,
} from "@/api/hooks/sessions"
import type { ActiveSession } from "@/types/Session"

const buildSession = (overrides: Partial<ActiveSession> = {}): ActiveSession =>
  ({
    id: overrides.id ?? "session-1",
    is_current: false,
    revoked_at: null,
    last_seen_at: "2026-05-08T12:00:00.000Z",
    created_at: "2026-05-08T11:00:00.000Z",
    user_agent: "Mozilla/5.0 / Test",
    ip_address: "127.0.0.1",
    ...overrides,
  }) as ActiveSession

describe("sessionsQueryKey", () => {
  it("returns the canonical 3-tuple shape ['auth','sessions',userId]", () => {
    expect(sessionsQueryKey("user-123")).toEqual(["auth", "sessions", "user-123"])
  })

  it("uses the 'me' fallback shape when no real user id", () => {
    expect(sessionsQueryKey("me")).toEqual(["auth", "sessions", "me"])
  })

  it("matches sessionsQueryOptions(userId).queryKey for the same userId", () => {
    expect(sessionsQueryOptions("user-x").queryKey).toEqual(sessionsQueryKey("user-x"))
  })
})

describe("sessionsQueryOptions", () => {
  it("preserves the W134 SW2 baseline: staleTime 30_000, gcTime 5min, networkMode online, retry 2", () => {
    const opts = sessionsQueryOptions("user-y")
    expect(opts.staleTime).toBe(30_000)
    expect(opts.gcTime).toBe(5 * 60_000)
    expect(opts.networkMode).toBe("online")
    expect(opts.retry).toBe(2)
    expect(typeof opts.retryDelay).toBe("function")
  })

  it("retryDelay caps at 10 seconds (FIX-68-05 mirror)", () => {
    const opts = sessionsQueryOptions("user-z")
    expect((opts.retryDelay as (n: number) => number)(0)).toBe(1_000)
    expect((opts.retryDelay as (n: number) => number)(1)).toBe(2_000)
    expect((opts.retryDelay as (n: number) => number)(10)).toBe(10_000)
  })
})

describe("updateSessionInCache (Wave 135 SW1)", () => {
  it("replaces the matching session by id and preserves siblings", () => {
    const client = new QueryClient()
    const session1 = buildSession({ id: "s1" })
    const session2 = buildSession({ id: "s2" })
    const session3 = buildSession({ id: "s3" })
    client.setQueryData(sessionsQueryKey("user-a"), [session1, session2, session3])

    const updated2 = buildSession({ id: "s2", revoked_at: "2026-05-08T12:30:00.000Z" })
    updateSessionInCache(client, "user-a", updated2)

    const after = client.getQueryData(sessionsQueryKey("user-a")) as ActiveSession[]
    expect(after).toHaveLength(3)
    expect(after[0]).toBe(session1)
    expect(after[1]?.id).toBe("s2")
    expect(after[1]?.revoked_at).toBe("2026-05-08T12:30:00.000Z")
    expect(after[2]).toBe(session3)
  })

  it("is a no-op when the cache slot is undefined (no setQueryData write)", () => {
    const client = new QueryClient()
    // Cache empty — passing arg should not error and should not write.
    updateSessionInCache(client, "user-b", buildSession({ id: "s1" }))
    // Confirm cache still empty for the slot.
    expect(client.getQueryData(sessionsQueryKey("user-b"))).toBeUndefined()
  })

  it("preserves non-array previous values defensively (no-op)", () => {
    const client = new QueryClient()
    // Defensive — should never happen, but guard via Array.isArray inside helper.
    client.setQueryData(sessionsQueryKey("user-c"), "not-an-array" as unknown)
    updateSessionInCache(client, "user-c", buildSession({ id: "s1" }))
    expect(client.getQueryData(sessionsQueryKey("user-c"))).toBe("not-an-array")
  })

  it("scopes the write to the correct userId slot (no cross-user leak)", () => {
    const client = new QueryClient()
    const userASession = buildSession({ id: "shared", user_agent: "user-a-ua" })
    const userBSession = buildSession({ id: "shared", user_agent: "user-b-ua" })
    client.setQueryData(sessionsQueryKey("user-a"), [userASession])
    client.setQueryData(sessionsQueryKey("user-b"), [userBSession])

    const updated = buildSession({ id: "shared", user_agent: "updated-for-a" })
    updateSessionInCache(client, "user-a", updated)

    const userAAfter = client.getQueryData(sessionsQueryKey("user-a")) as ActiveSession[]
    const userBAfter = client.getQueryData(sessionsQueryKey("user-b")) as ActiveSession[]
    expect(userAAfter[0]?.user_agent).toBe("updated-for-a")
    expect(userBAfter[0]?.user_agent).toBe("user-b-ua")
  })
})

describe("invalidateSessions (Wave 135 SW1)", () => {
  it("invalidates the sessionsQueryKey(userId) slot only", async () => {
    const client = new QueryClient()
    const spy = vi.spyOn(client, "invalidateQueries")
    await invalidateSessions(client, "user-d")
    expect(spy).toHaveBeenCalledWith({ queryKey: sessionsQueryKey("user-d") })
  })

  it("returns the underlying invalidateQueries promise (awaitable)", async () => {
    const client = new QueryClient()
    const result = invalidateSessions(client, "user-e")
    expect(result).toBeInstanceOf(Promise)
    await expect(result).resolves.toBeUndefined()
  })
})
