/**
 * @fileoverview Wave 129 polish + Wave 130 SW3 — direct unit tests for the SSR factories.
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
 *   - scheduleGroupsQueryOptions() (W130 SW1): queryKey shape + staleTime
 *     + retry + retryDelay (FIX-68-05) preservation
 *   - pageScheduleQueryOptions(groupId) (W130 SW1): queryKey shape with/
 *     without groupId + enabled flag + staleTime
 *   - weatherQueryOptions(coordinates) (W130 SW3): queryKey shape with
 *     4-decimal coordinate precision + staleTime + placeholderData
 *     fallback path (sessionStorage cold-mount)
 */
import { QueryClient } from "@tanstack/react-query"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

import { eventDetailQueryOptions } from "../events"
import { newsDetailQueryOptions, prefetchNewsListQuery } from "../news"
import { scheduleGroupsQueryOptions, pageScheduleQueryOptions } from "../schedule"
import { sessionsQueryKey, sessionsQueryOptions } from "../sessions"
import { currentUserQueryOptions, currentUserQueryKey } from "../users"
import { weatherQueryOptions, weatherQueryKey } from "../weather"

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

describe("scheduleGroupsQueryOptions (Wave 130 SW1)", () => {
  it("queryKey shape is ['schedule', 'groups']", () => {
    const opts = scheduleGroupsQueryOptions()
    expect(opts.queryKey).toEqual(["schedule", "groups"])
  })

  it("staleTime is 60_000 (matches useScheduleData baseline)", () => {
    const opts = scheduleGroupsQueryOptions()
    expect(opts.staleTime).toBe(60_000)
  })

  it("gcTime is 5 * 60_000", () => {
    const opts = scheduleGroupsQueryOptions()
    expect(opts.gcTime).toBe(5 * 60_000)
  })

  it("retry is 2 (FIX-68-05 mobile flake budget preserved)", () => {
    const opts = scheduleGroupsQueryOptions()
    expect(opts.retry).toBe(2)
  })

  it("retryDelay applies exponential backoff capped at 10s", () => {
    const opts = scheduleGroupsQueryOptions()
    // 1000 * 2^0 = 1000; 1000 * 2^4 = 16000 capped to 10000
    expect(opts.retryDelay(0)).toBe(1000)
    expect(opts.retryDelay(1)).toBe(2000)
    expect(opts.retryDelay(4)).toBe(10_000)
    expect(opts.retryDelay(10)).toBe(10_000)
  })

  it("queryFn is callable", () => {
    const opts = scheduleGroupsQueryOptions()
    expect(typeof opts.queryFn).toBe("function")
  })
})

describe("pageScheduleQueryOptions (Wave 130 SW1)", () => {
  it("queryKey for non-null groupId is ['schedule', 'group', groupId]", () => {
    const opts = pageScheduleQueryOptions("group-abc")
    expect(opts.queryKey).toEqual(["schedule", "group", "group-abc"])
  })

  it("queryKey for null groupId is ['schedule', 'group', 'none']", () => {
    const opts = pageScheduleQueryOptions(null)
    expect(opts.queryKey).toEqual(["schedule", "group", "none"])
  })

  it("enabled is true when groupId is non-null", () => {
    expect(pageScheduleQueryOptions("g1").enabled).toBe(true)
  })

  it("enabled is false when groupId is null", () => {
    expect(pageScheduleQueryOptions(null).enabled).toBe(false)
  })

  it("staleTime + gcTime + retry + retryDelay match useScheduleData baseline", () => {
    const opts = pageScheduleQueryOptions("g1")
    expect(opts.staleTime).toBe(60_000)
    expect(opts.gcTime).toBe(5 * 60_000)
    expect(opts.retry).toBe(2)
    expect(opts.retryDelay(0)).toBe(1000)
  })

  it("queryFn returns [] when groupId is null (defensive)", async () => {
    const opts = pageScheduleQueryOptions(null)
    // queryFn signature requires QueryFunctionContext but the null-groupId
    // path returns [] before reading any context — pass {} cast to bypass
    // type narrowing for this defensive smoke test.
    const result = await opts.queryFn({ signal: undefined } as never)
    expect(result).toEqual([])
  })
})

describe("weatherQueryOptions (Wave 130 SW3)", () => {
  beforeEach(() => {
    if (typeof window !== "undefined" && window.sessionStorage) {
      window.sessionStorage.clear()
    }
  })

  it("queryKey shape is ['weather', 'snapshot', latStr, lonStr] with 4-decimal precision", () => {
    const opts = weatherQueryOptions({ lat: 55.71467, lon: 37.81652 })
    expect(opts.queryKey).toEqual(["weather", "snapshot", "55.7147", "37.8165"])
  })

  it("weatherQueryKey identical for coordinates rounded to same 4 decimals", () => {
    const k1 = weatherQueryKey({ lat: 55.71467, lon: 37.81652 })
    const k2 = weatherQueryKey({ lat: 55.71471, lon: 37.81649 })
    expect(k1).toEqual(k2) // both round to ['weather', 'snapshot', '55.7147', '37.8165']
  })

  it("weatherQueryKey differs for coordinates with different 4-decimal rounding", () => {
    const k1 = weatherQueryKey({ lat: 55.71467, lon: 37.81652 })
    const k2 = weatherQueryKey({ lat: 55.7152, lon: 37.81652 })
    expect(k1).not.toEqual(k2)
  })

  it("staleTime defaults to WEATHER_CACHE_TTL_MS (10 min)", () => {
    const opts = weatherQueryOptions({ lat: 0, lon: 0 })
    expect(opts.staleTime).toBe(10 * 60_000)
  })

  it("staleTime override propagates", () => {
    const opts = weatherQueryOptions({ lat: 0, lon: 0 }, 5 * 60_000)
    expect(opts.staleTime).toBe(5 * 60_000)
  })

  it("gcTime is 30 minutes (longer retention than staleTime)", () => {
    const opts = weatherQueryOptions({ lat: 0, lon: 0 })
    expect(opts.gcTime).toBe(30 * 60_000)
  })

  it("retry is 1 (limits external API hammering on transient failures)", () => {
    const opts = weatherQueryOptions({ lat: 0, lon: 0 })
    expect(opts.retry).toBe(1)
  })

  it("refetchOnWindowFocus + refetchOnMount disabled (avoid spam)", () => {
    const opts = weatherQueryOptions({ lat: 0, lon: 0 })
    expect(opts.refetchOnWindowFocus).toBe(false)
    expect(opts.refetchOnMount).toBe(false)
  })

  it("placeholderData returns undefined when sessionStorage is empty", () => {
    const opts = weatherQueryOptions({ lat: 55.71467, lon: 37.81652 })
    expect(opts.placeholderData()).toBeUndefined()
  })

  it("placeholderData returns sessionStorage cached snapshot when present", () => {
    const coords = { lat: 55.71467, lon: 37.81652 }
    const fakeSnapshot = {
      conditionCode: 0,
      conditionLabel: "Clear",
      temperatureC: 18.5,
      observedAt: "2026-05-06T12:00:00.000Z",
    }
    // Same key shape readWeatherCache uses (`weather:snapshot:LAT,LON`)
    window.sessionStorage.setItem(
      "weather:snapshot:55.7147,37.8165",
      JSON.stringify({ data: fakeSnapshot, expiresAt: Date.now() + 600_000 })
    )

    const opts = weatherQueryOptions(coords)
    expect(opts.placeholderData()).toEqual(fakeSnapshot)
  })

  it("placeholderData allowExpired returns expired sessionStorage entry (fallback paint)", () => {
    const coords = { lat: 55.71467, lon: 37.81652 }
    const fakeSnapshot = {
      conditionCode: 1,
      conditionLabel: "Cloudy",
      temperatureC: 12.0,
      observedAt: "2026-05-06T11:00:00.000Z",
    }
    // expiresAt in the past — placeholderData passes allowExpired: true
    window.sessionStorage.setItem(
      "weather:snapshot:55.7147,37.8165",
      JSON.stringify({ data: fakeSnapshot, expiresAt: Date.now() - 60_000 })
    )

    const opts = weatherQueryOptions(coords)
    expect(opts.placeholderData()).toEqual(fakeSnapshot)
  })

  it("queryFn is callable", () => {
    const opts = weatherQueryOptions({ lat: 0, lon: 0 })
    expect(typeof opts.queryFn).toBe("function")
  })
})

describe("currentUserQueryOptions (Wave 133 SW2)", () => {
  it("queryKey shape is the stable readonly tuple ['users', 'me']", () => {
    expect(currentUserQueryKey).toEqual(["users", "me"])
  })

  it("returned options expose the same queryKey reference (cache identity)", () => {
    const opts = currentUserQueryOptions()
    expect(opts.queryKey).toBe(currentUserQueryKey)
  })

  it("staleTime is 60_000 (matches schedule.ts pattern)", () => {
    const opts = currentUserQueryOptions()
    expect(opts.staleTime).toBe(60_000)
  })

  it("gcTime is 5 * 60_000 (matches schedule.ts pattern)", () => {
    const opts = currentUserQueryOptions()
    expect(opts.gcTime).toBe(5 * 60_000)
  })

  it("networkMode is 'online' (no SSR background-refetch on offline)", () => {
    const opts = currentUserQueryOptions()
    expect(opts.networkMode).toBe("online")
  })

  it("retry is 2 (mirrors schedule.ts; FIX-68-05 mobile flakiness)", () => {
    const opts = currentUserQueryOptions()
    expect(opts.retry).toBe(2)
  })

  it("retryDelay is exponential (1000 * 2^attempt, capped at 10_000)", () => {
    const opts = currentUserQueryOptions()
    expect(typeof opts.retryDelay).toBe("function")
    if (typeof opts.retryDelay !== "function") return
    expect(opts.retryDelay(0)).toBe(1_000)
    expect(opts.retryDelay(1)).toBe(2_000)
    expect(opts.retryDelay(2)).toBe(4_000)
    expect(opts.retryDelay(3)).toBe(8_000)
    expect(opts.retryDelay(4)).toBe(10_000) // capped
    expect(opts.retryDelay(10)).toBe(10_000) // still capped
  })

  it("queryFn is a function (callable; signal-bearing AbortController forwarded)", () => {
    const opts = currentUserQueryOptions()
    expect(typeof opts.queryFn).toBe("function")
  })

  it("returns a fresh options object per call (not memoized — caller's responsibility)", () => {
    const a = currentUserQueryOptions()
    const b = currentUserQueryOptions()
    expect(a).not.toBe(b)
    // Same shape though — and the queryKey reference IS shared (stable readonly tuple)
    expect(a.queryKey).toBe(b.queryKey)
    expect(a.staleTime).toBe(b.staleTime)
  })
})

describe("sessionsQueryOptions (Wave 134 SW2)", () => {
  it("queryKey shape is ['auth', 'sessions', userId]", () => {
    const opts = sessionsQueryOptions("user-1")
    expect(opts.queryKey).toEqual(["auth", "sessions", "user-1"])
  })

  it("queryKey reflects userId verbatim (no normalization)", () => {
    expect(sessionsQueryOptions("11111111-1111-1111-1111-111111111111").queryKey[2]).toBe(
      "11111111-1111-1111-1111-111111111111"
    )
    expect(sessionsQueryOptions("me").queryKey[2]).toBe("me")
  })

  it("queryKey shape preserved across factory refactor (cache identity)", () => {
    // Pre-W134 useSessionManagement used inline ["auth", "sessions", user?.id ?? "me"].
    // The factory MUST produce the SAME tuple shape so SSR-prefetched entries
    // (loader-side ensureQueryData) hydrate cleanly into the client-side
    // useQuery consumer (useSessionManagement). Drift would silently break
    // cache identity → client refetches even when SSR already populated cache.
    expect(sessionsQueryKey("user-1")).toEqual(["auth", "sessions", "user-1"])
    expect(sessionsQueryOptions("user-1").queryKey).toEqual(sessionsQueryKey("user-1"))
  })

  it("staleTime is 30_000 (matches pre-W134 useSessionManagement default)", () => {
    expect(sessionsQueryOptions("user-1").staleTime).toBe(30_000)
  })

  it("gcTime is 5 * 60_000 (default schedule.ts pattern)", () => {
    expect(sessionsQueryOptions("user-1").gcTime).toBe(5 * 60_000)
  })

  it("networkMode is 'online'", () => {
    expect(sessionsQueryOptions("user-1").networkMode).toBe("online")
  })

  it("retry is 2 with exponential retryDelay (FIX-68-05)", () => {
    const opts = sessionsQueryOptions("user-1")
    expect(opts.retry).toBe(2)
    expect(typeof opts.retryDelay).toBe("function")
    if (typeof opts.retryDelay !== "function") return
    expect(opts.retryDelay(0)).toBe(1_000)
    expect(opts.retryDelay(1)).toBe(2_000)
    expect(opts.retryDelay(2)).toBe(4_000)
    expect(opts.retryDelay(4)).toBe(10_000) // capped
  })

  it("queryFn is callable (signal-bearing AbortController forwarded)", () => {
    expect(typeof sessionsQueryOptions("user-1").queryFn).toBe("function")
  })

  it("queryKey tuple instances are NOT reference-equal across calls (acceptable — useQuery deep-compares)", () => {
    // Unlike currentUserQueryOptions which exports a stable readonly
    // tuple constant, sessionsQueryKey produces a fresh tuple per call
    // (the userId is parameterised). useQuery + ensureQueryData both
    // deep-compare queryKey, so this is fine for cache identity.
    const a = sessionsQueryKey("user-1")
    const b = sessionsQueryKey("user-1")
    expect(a).not.toBe(b)
    expect(a).toEqual(b)
  })
})
