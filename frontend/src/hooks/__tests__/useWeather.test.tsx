import { renderHook, act, waitFor } from "@testing-library/react"
import { vi, describe, it, expect, beforeEach } from "vitest"
import { useWeather } from "../useWeather"
import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import React from "react"

// Mock fetchWeatherSnapshot
const mockFetchWeatherSnapshot = vi.fn()
vi.mock("@/api/weather", () => ({
  WEATHER_CACHE_TTL_MS: 300000,
  fetchWeatherSnapshot: (...args: unknown[]) => mockFetchWeatherSnapshot(...args),
}))

// Mock weatherQueryOptions
vi.mock("@/api/hooks/weather", () => ({
  weatherQueryOptions: (coords: unknown, ttl: number) => ({
    queryKey: ["weather", coords, ttl],
  }),
}))

// Mock useMediaQuery
const mockUseMediaQuery = vi.fn(() => false)
vi.mock("../useMediaQuery", () => ({
  default: () => mockUseMediaQuery(),
}))

// Mock getWeatherIconMeta
vi.mock("@/utils/weatherIcons", () => ({
  getWeatherIconMeta: (_code: string) => ({
    icon: "mock-icon",
    translationKeySuffix: "mock-suffix",
    animation: "pulse",
  }),
}))

describe("useWeather", () => {
  let queryClient: QueryClient

  const wrapper = ({ children }: { children: React.ReactNode }) => (
    <QueryClientProvider client={queryClient}>{children}</QueryClientProvider>
  )

  beforeEach(() => {
    vi.clearAllMocks()
    queryClient = new QueryClient({
      defaultOptions: {
        queries: {
          retry: false,
        },
      },
    })
  })

  it("handles loading and successful data fetching with defaults", async () => {
    mockFetchWeatherSnapshot.mockResolvedValue({
      temp: 22,
      conditionCode: "clear",
    })

    const { result } = renderHook(() => useWeather(), { wrapper })

    expect(result.current.isLoading).toBe(true)
    expect(result.current.data).toBeNull()

    // Wait for the query to resolve
    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.data).toEqual({
      temp: 22,
      conditionCode: "clear",
      icon: "mock-icon",
      translationKeySuffix: "mock-suffix",
      translationKey: "dashboard:weather.conditions.mock-suffix",
      animation: "pulse",
    })
    expect(result.current.error).toBeNull()
  })

  it("applies overrides and handles error states", async () => {
    const customCoords = { lat: 10, lon: 20 }
    const customTtl = 5000
    mockFetchWeatherSnapshot.mockRejectedValue(new Error("Network Error"))

    const { result } = renderHook(
      () => useWeather({ coordinates: customCoords, cacheTtlMs: customTtl }),
      { wrapper }
    )

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.data).toBeNull()
    expect(result.current.error?.message).toBe("Network Error")
  })

  it("honours forceRefresh during refresh call", async () => {
    mockFetchWeatherSnapshot.mockResolvedValue({
      temp: 18,
      conditionCode: "cloudy",
    })

    const { result } = renderHook(() => useWeather(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(mockFetchWeatherSnapshot).toHaveBeenLastCalledWith(
      expect.objectContaining({ forceRefresh: false })
    )

    // Call refresh
    await act(async () => {
      await result.current.refresh()
    })

    expect(mockFetchWeatherSnapshot).toHaveBeenLastCalledWith(
      expect.objectContaining({ forceRefresh: true })
    )
  })

  it("sets animation to none if prefersReducedMotion is active", async () => {
    mockUseMediaQuery.mockReturnValue(true)
    mockFetchWeatherSnapshot.mockResolvedValue({
      temp: 25,
      conditionCode: "sunny",
    })

    const { result } = renderHook(() => useWeather(), { wrapper })

    await waitFor(() => expect(result.current.isLoading).toBe(false))

    expect(result.current.data?.animation).toBe("none")
  })
})
