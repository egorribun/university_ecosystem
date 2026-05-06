/**
 * @fileoverview Wave 129 polish — direct unit tests for the 3 new SSR factories.
 *
 * Closes part of the W129 vitest-delta-zero honesty caveat. Although the
 * factories are pure pass-through wrappers (their queryFn behavior is
 * exercised indirectly through the existing hook tests), explicit shape
 * verification is still useful as a regression guard against accidental
 * queryKey shape changes (which would invalidate cache entries on
 * hydration — see W129 SW5 honest deferral #10).
 *
 * Coverage:
 *   - eventDetailQueryOptions(id): queryKey shape + staleTime + retry
 *   - newsDetailQueryOptions(id, language): queryKey shape (W129 SW5
 *     deliberately preserves the legacy ["news", id, language] shape over
 *     a more-consistent ["news", "detail", id, language] for cache
 *     identity preservation)
 *   - prefetchNewsListQuery(qc, filters): invokes prefetchInfiniteQuery on
 *     the provided QueryClient with the cursor pagination shape
 */
import { QueryClient } from "@tanstack/react-query"
import { afterEach, describe, expect, it, vi } from "vitest"

import { eventDetailQueryOptions } from "../events"
import { newsDetailQueryOptions, prefetchNewsListQuery } from "../news"

// TanStack Query's `FetchInfiniteQueryOptions` is a discriminated union over
// `pages?: number` — when `pages` is undefined the type narrows to a branch
// that doesn't expose `getNextPageParam`. The runtime values DO include it
// (cursor pagination shape mirrored from events.ts:261-272), so this loose
// shape is used for spy.mock.calls[0]?.[0] inspection in the prefetch tests.
type CapturedPrefetchOptions = {
  queryKey: readonly [string, string, { language: string; limit: number }]
  initialPageParam: string | null
  getNextPageParam: (lastPage: { next_cursor: string | null }) => string | null
}

describe("eventDetailQueryOptions (Wave 129 SW2)", () => {
  it("queryKey shape is ['events', 'detail', id]", () => {
    const opts = eventDetailQueryOptions("abc-123")
    expect(opts.queryKey).toEqual(["events", "detail", "abc-123"])
  })

  it("queryKey id is reflected as-is (no normalization)", () => {
    const opts = eventDetailQueryOptions("11111111-1111-1111-1111-111111111111")
    expect(opts.queryKey[2]).toBe("11111111-1111-1111-1111-111111111111")
  })

  it("staleTime is 60_000 (60s — matches W129 SW2 plan)", () => {
    const opts = eventDetailQueryOptions("any-id")
    expect(opts.staleTime).toBe(60_000)
  })

  it("retry is 1 (limits SSR loader latency on network blips)", () => {
    const opts = eventDetailQueryOptions("any-id")
    expect(opts.retry).toBe(1)
  })

  it("queryFn is a function (callable)", () => {
    const opts = eventDetailQueryOptions("any-id")
    expect(typeof opts.queryFn).toBe("function")
  })

  it("returns a fresh options object per call (not memoized — caller's responsibility)", () => {
    const a = eventDetailQueryOptions("id-1")
    const b = eventDetailQueryOptions("id-1")
    expect(a).not.toBe(b)
    // Same shape though
    expect(a.queryKey).toEqual(b.queryKey)
    expect(a.staleTime).toBe(b.staleTime)
  })
})

describe("newsDetailQueryOptions (Wave 129 SW5)", () => {
  it("queryKey shape is legacy ['news', id, language] — backward-compat preserved", () => {
    const opts = newsDetailQueryOptions("abc-123", "ru")
    expect(opts.queryKey).toEqual(["news", "abc-123", "ru"])
  })

  it("queryKey shape NOT modernized to ['news', 'detail', id, language] (W129 SW5 deferral #10)", () => {
    const opts = newsDetailQueryOptions("abc-123", "en")
    // The legacy shape is preserved deliberately to avoid invalidating
    // existing client-side cache entries on hydration. If a future wave
    // changes this, the migration must invalidate cache or accept a brief
    // refetch on first hydration after deploy.
    expect(opts.queryKey.length).toBe(3)
    expect(opts.queryKey[0]).toBe("news")
    expect(opts.queryKey[1]).toBe("abc-123") // id, NOT "detail"
    expect(opts.queryKey[2]).toBe("en")
  })

  it("queryKey reflects different language values", () => {
    const ru = newsDetailQueryOptions("same-id", "ru")
    const en = newsDetailQueryOptions("same-id", "en")
    expect(ru.queryKey).not.toEqual(en.queryKey)
    expect(ru.queryKey[2]).toBe("ru")
    expect(en.queryKey[2]).toBe("en")
  })

  it("staleTime is 60_000 (matches in-component pre-W129 useQuery)", () => {
    const opts = newsDetailQueryOptions("any-id", "ru")
    expect(opts.staleTime).toBe(60_000)
  })

  it("retry is 1", () => {
    const opts = newsDetailQueryOptions("any-id", "ru")
    expect(opts.retry).toBe(1)
  })

  it("queryFn is a function (callable)", () => {
    const opts = newsDetailQueryOptions("any-id", "ru")
    expect(typeof opts.queryFn).toBe("function")
  })
})

describe("prefetchNewsListQuery (Wave 129 SW3)", () => {
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it("invokes queryClient.prefetchInfiniteQuery with cursor pagination shape", async () => {
    const qc = new QueryClient()
    // Spy on prefetchInfiniteQuery without invoking the real fetcher.
    // The factory's queryFn references network code that we don't want to
    // exercise here — the existing useNewsListQuery hook tests cover that.
    const spy = vi.spyOn(qc, "prefetchInfiniteQuery").mockResolvedValue(undefined)

    await prefetchNewsListQuery(qc, { language: "ru" })

    expect(spy).toHaveBeenCalledOnce()
    const passedOptions = spy.mock.calls[0]?.[0] as unknown as CapturedPrefetchOptions
    expect(passedOptions).toBeDefined()
    expect(passedOptions.queryKey[0]).toBe("news")
    expect(passedOptions.queryKey[1]).toBe("list")
    // initialPageParam null + getNextPageParam returning lastPage.next_cursor
    // is the cursor-pagination shape mirrored from events.ts:261-272.
    expect(passedOptions.initialPageParam).toBeNull()
    expect(typeof passedOptions.getNextPageParam).toBe("function")
  })

  it("normalizes filters into queryKey[2] (limit defaults applied)", async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, "prefetchInfiniteQuery").mockResolvedValue(undefined)

    await prefetchNewsListQuery(qc, { language: "en" })

    const passedOptions = spy.mock.calls[0]?.[0] as unknown as CapturedPrefetchOptions
    const normalizedKey = passedOptions.queryKey[2]
    expect(normalizedKey.language).toBe("en")
    expect(normalizedKey.limit).toBe(12) // NEWS_PAGE_SIZE default
  })

  it("getNextPageParam returns lastPage.next_cursor (or null)", async () => {
    const qc = new QueryClient()
    const spy = vi.spyOn(qc, "prefetchInfiniteQuery").mockResolvedValue(undefined)

    await prefetchNewsListQuery(qc, { language: "ru" })

    const passedOptions = spy.mock.calls[0]?.[0] as unknown as CapturedPrefetchOptions
    const { getNextPageParam } = passedOptions

    expect(getNextPageParam({ next_cursor: "cursor-abc" })).toBe("cursor-abc")
    expect(getNextPageParam({ next_cursor: null })).toBeNull()
  })

  it("returns the prefetchInfiniteQuery promise (caller can await)", async () => {
    const qc = new QueryClient()
    const sentinel = Symbol("resolved-value")
    vi.spyOn(qc, "prefetchInfiniteQuery").mockResolvedValue(sentinel as never)

    const result = await prefetchNewsListQuery(qc, { language: "ru" })
    expect(result).toBe(sentinel)
  })
})
