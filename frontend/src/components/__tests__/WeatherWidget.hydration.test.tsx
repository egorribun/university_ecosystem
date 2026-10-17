import { QueryClient, QueryClientProvider } from "@tanstack/react-query"
import { act, waitFor } from "@testing-library/react"
import { hydrateRoot, type Root } from "react-dom/client"
import { renderToString } from "react-dom/server"
import { afterEach, describe, expect, it, vi } from "vitest"

import { CAMPUS_COORDINATES } from "@/constants/campus"
import WeatherWidget from "@/components/ui/WeatherWidget"

vi.mock("react-i18next", () => ({
  useTranslation: () => ({
    t: (key: string, options?: { defaultValue?: string }) => options?.defaultValue ?? key,
  }),
}))

vi.mock("@/i18n/formatters", () => ({
  useLocaleFormatters: () => ({
    formatNumber: (value: number, options?: Intl.NumberFormatOptions) =>
      new Intl.NumberFormat("en-US", options).format(value),
  }),
}))

const cacheKey = `weather:snapshot:${Number(CAMPUS_COORDINATES.lat).toFixed(4)},${Number(
  CAMPUS_COORDINATES.lon
).toFixed(4)}`

const createQueryClient = () =>
  new QueryClient({ defaultOptions: { queries: { retry: false, gcTime: Infinity } } })

describe("WeatherWidget SSR hydration", () => {
  let root: Root | undefined
  let container: HTMLDivElement | undefined
  let serverClient: QueryClient | undefined
  let browserClient: QueryClient | undefined
  let previousCacheValue: string | null = null

  afterEach(async () => {
    if (root) {
      await act(async () => root?.unmount())
      root = undefined
    }
    container?.remove()
    container = undefined
    serverClient?.clear()
    browserClient?.clear()
    serverClient = undefined
    browserClient = undefined
    if (typeof window !== "undefined") {
      if (previousCacheValue === null) window.sessionStorage.removeItem(cacheKey)
      else window.sessionStorage.setItem(cacheKey, previousCacheValue)
    }
    previousCacheValue = null
    vi.restoreAllMocks()
  })

  it("hydrates the server loading state before showing the retained session cache", async () => {
    previousCacheValue = window.sessionStorage.getItem(cacheKey)
    const cachedSnapshot = {
      conditionCode: 0,
      conditionLabel: "Clear sky",
      temperatureC: 18.5,
      observedAt: "2026-10-09T08:00:00.000Z",
    }
    const cacheEntry = {
      data: cachedSnapshot,
      expiresAt: Date.now() + 60_000,
    }
    window.sessionStorage.setItem(cacheKey, JSON.stringify(cacheEntry))

    serverClient = createQueryClient()
    browserClient = createQueryClient()
    const originalWindow = Object.getOwnPropertyDescriptor(globalThis, "window")
    if (!originalWindow) throw new Error("Expected the jsdom window descriptor")

    let serverMarkup: string
    try {
      Object.defineProperty(globalThis, "window", { configurable: true, value: undefined })
      serverMarkup = renderToString(
        <QueryClientProvider client={serverClient}>
          <WeatherWidget />
        </QueryClientProvider>
      )
    } finally {
      Object.defineProperty(globalThis, "window", originalWindow)
    }

    expect(serverMarkup).toContain("chip-weather__skeleton")

    container = document.createElement("div")
    container.innerHTML = serverMarkup
    document.body.append(container)
    const recoverableErrors: unknown[] = []
    const fetchSpy = vi
      .spyOn(globalThis, "fetch")
      .mockRejectedValue(new Error("Unexpected weather network request"))

    await act(async () => {
      root = hydrateRoot(
        container as HTMLDivElement,
        <QueryClientProvider client={browserClient as QueryClient}>
          <WeatherWidget />
        </QueryClientProvider>,
        { onRecoverableError: (error) => recoverableErrors.push(error) }
      )
    })

    expect(recoverableErrors).toEqual([])
    await waitFor(() =>
      expect(container?.querySelector(".chip-weather__temp")).toHaveTextContent("+19°")
    )
    expect(window.sessionStorage.getItem(cacheKey)).toBe(JSON.stringify(cacheEntry))
    expect(fetchSpy).not.toHaveBeenCalled()
  })
})
