/**
 * @fileoverview Tests for weather.ts API hook exports (queryFn execution).
 *
 * Complements `ssrFactories.test.ts` (which tests factory shape and
 * placeholderData) with queryFn execution tests that mock
 * `fetchWeatherSnapshot` and verify signal forwarding, coordinate + cacheTtl
 * argument forwarding, and error propagation.
 *
 * Coverage:
 *   - weatherQueryKey(): coordinate rounding (re-verified for completeness)
 *   - weatherQueryOptions().queryFn: delegates to fetchWeatherSnapshot,
 *     forwards coordinates + cacheTtlMs + signal
 */
import { QueryClient, QueryClientProvider, useQuery } from "@tanstack/react-query"
import { renderHook, waitFor } from "@testing-library/react"
import type { PropsWithChildren } from "react"
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest"

// ── Mock the weather API helper ─────────────────────────────────────────────
const fetchWeatherSnapshotMock = vi.hoisted(() => vi.fn())
const readWeatherCacheMock = vi.hoisted(() => vi.fn())
vi.mock("@/api/weather", () => ({
  fetchWeatherSnapshot: fetchWeatherSnapshotMock,
  readWeatherCache: readWeatherCacheMock,
  WEATHER_CACHE_TTL_MS: 10 * 60_000,
}))

import { weatherQueryKey, weatherQueryOptions } from "@/api/hooks/weather"

// ── Helpers ─────────────────────────────────────────────────────────────────
const makeWrapper = (queryClient: QueryClient) => {
  const Wrapper = ({ children }: PropsWithChildren) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )
  return Wrapper
}

const createQueryClient = () =>
  new QueryClient({
    defaultOptions: { queries: { retry: false, gcTime: 0 } },
  })

const COORDS = { lat: 55.71467, lon: 37.81652 }

const WEATHER_STUB = {
  conditionCode: 0,
  conditionLabel: "Clear",
  temperatureC: 22.5,
  observedAt: "2026-06-28T12:00:00.000Z",
}

afterEach(() => {
  vi.restoreAllMocks()
})

// ── weatherQueryKey ─────────────────────────────────────────────────────────
describe("weatherQueryKey", () => {
  it("rounds coordinates to 4 decimal places", () => {
    expect(weatherQueryKey(COORDS)).toEqual(["weather", "snapshot", "55.7147", "37.8165"])
  })

  it("integer coordinates produce '.0000' suffix", () => {
    expect(weatherQueryKey({ lat: 0, lon: 0 })).toEqual(["weather", "snapshot", "0.0000", "0.0000"])
  })
})

// ── weatherQueryOptions queryFn execution ───────────────────────────────────
describe("weatherQueryOptions queryFn execution", () => {
  let queryClient: QueryClient

  beforeEach(() => {
    queryClient = createQueryClient()
    readWeatherCacheMock.mockReturnValue(null)
  })

  it("fetches weather data and returns snapshot on success", async () => {
    fetchWeatherSnapshotMock.mockResolvedValueOnce(WEATHER_STUB)

    const { result } = renderHook(
      () => {
        return useQuery(weatherQueryOptions(COORDS))
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(result.current.data).toEqual(WEATHER_STUB)
  })

  it("forwards coordinates, cacheTtlMs, and signal to fetchWeatherSnapshot", async () => {
    fetchWeatherSnapshotMock.mockResolvedValueOnce(WEATHER_STUB)
    const customTtl = 5 * 60_000

    const { result } = renderHook(
      () => {
        return useQuery(weatherQueryOptions(COORDS, customTtl))
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isSuccess).toBe(true))

    expect(fetchWeatherSnapshotMock).toHaveBeenCalledWith({
      coordinates: COORDS,
      cacheTtlMs: customTtl,
      signal: expect.any(AbortSignal),
    })
  })

  it("enters error state when fetchWeatherSnapshot fails", async () => {
    fetchWeatherSnapshotMock.mockRejectedValueOnce(new Error("API rate limit"))

    const { result } = renderHook(
      () => {
        return useQuery({ ...weatherQueryOptions(COORDS), retry: false })
      },
      { wrapper: makeWrapper(queryClient) }
    )

    await waitFor(() => expect(result.current.isError).toBe(true))

    //("API rate limit")
  })

  it("placeholderData uses readWeatherCache with allowExpired", () => {
    readWeatherCacheMock.mockReturnValue({ data: WEATHER_STUB })

    const opts = weatherQueryOptions(COORDS)
    const placeholder = opts.placeholderData()

    expect(placeholder).toEqual(WEATHER_STUB)
    expect(readWeatherCacheMock).toHaveBeenCalledWith(COORDS, {
      allowExpired: true,
    })
  })

  it("placeholderData returns undefined when cache is empty", () => {
    readWeatherCacheMock.mockReturnValue(null)

    const opts = weatherQueryOptions(COORDS)
    expect(opts.placeholderData()).toBeUndefined()
  })
})
